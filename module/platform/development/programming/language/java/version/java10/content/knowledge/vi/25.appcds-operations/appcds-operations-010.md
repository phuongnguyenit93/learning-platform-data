# Tạo lại kho AppCDS khi đổi JDK hoặc đầu vào được lưu trữ

*Ngữ cảnh: Java 10 — Vận hành AppCDS (Application Class-Data Sharing). Trọng tâm của bài là **khi nào phải tạo lại archive**, vì sao cùng một tệp `.jsa` không luôn dùng lại được sau thay đổi JDK/JAR/classpath, cách kiểm tra và khôi phục đúng, cùng chiến lược CI/CD hiện đại. Các ví dụ Java biên dịch bằng `--release 17` và các cờ HotSpot đã được kiểm thử trên JDK 24. Phần AOT cache của JDK 24/25 được tách riêng theo phiên bản.*

## 1. Kết luận quan trọng nhất

**AppCDS archive không phải tệp cache “portable vô hạn”.** Nội dung nó gắn với **JDK build** tạo ra nó và những **class/JAR/module path cùng các điều kiện nạp lớp** tại thời điểm sinh archive. Thay đổi những đầu vào có thể làm archive **không còn dùng được**. Khi có thay đổi không tương thích, hãy **thu thập lại class được nạp bằng build mới** và **tạo lại archive bằng đúng JDK/runtime sẽ triển khai**.

Ví dụ:

~~~text
Build v1:
  JDK A + app.jar v1 + classpath đã chốt
        |
        v
  app.classlist + app.jsa  ──────> JVM chạy v1: dùng archive

Build v2:
  JDK A + app.jar v2 (đã thay class bytecode)
        |
        v
  app.jsa cũ từ v1  ─────────────> Có thể bị từ chối vì JAR đã đổi
        |
        v
  Thu class list mới + tạo app-v2.jsa ─> JVM chạy v2: dùng archive mới
~~~

Khi đổi **JDK A sang JDK B**, ngay cả khi `app.jar` không thay đổi, cũng không nên dùng lại archive tạo bởi JDK A. Nội dung archive gắn với runtime image/JDK build cụ thể, không chỉ với Java feature number như `17` hoặc `21`.

Đối với **mã nguồn cấu hình thay đổi nhưng không đổi classpath/JAR**, cần phân biệt: archive có thể vẫn **hợp lệ về mặt kỹ thuật**, nhưng tập class đã ghi nhận từ workload cũ có thể **không còn tối ưu** cho startup/first-request mới. Có trường hợp cần **retrain để nâng hiệu suất**, dù JVM không báo lỗi.

**Một quy tắc vận hành:** Sau mỗi thay đổi đầu vào liên quan, hãy kiểm tra **archive được dùng thật**, **ứng dụng chạy đúng**, rồi **đo hiệu năng**; không đánh đồng ba tiêu chí này.

## 2. AppCDS archive lưu cái gì?

`CDS` (*Class Data Sharing*) của HotSpot lưu thông tin đã xử lý của các Java class vào một tệp archive để JVM có thể dùng lại, giúp tối ưu việc nạp class, startup và khả năng chia sẻ metadata giữa tiến trình phù hợp. `AppCDS`, được đưa vào Java 10 theo **JEP 310**, mở rộng khả năng archive những lớp từ ứng dụng và thư viện ngoài lớp nền JDK.

Những tệp thường gặp:

| Tệp/đầu vào | Vai trò | Có cần tạo lại khi đổi build? |
| --- | --- | --- |
| `app.jar`, các dependency JAR | Chứa class cần chạy | Là artifact ứng dụng gốc |
| `app.classlist` | Danh sách class được nạp trong lượt training | **Thu lại** nếu class/workload hoặc JDK đổi làm danh sách cũ thiếu hoặc không khớp |
| `app.jsa` | Static AppCDS archive | **Tạo lại** khi JDK/JAR/module hoặc những điều kiện ràng buộc không còn tương thích |
| `app-dynamic.jsa` | Dynamic CDS archive được tạo sau training | **Tạo lại** theo JDK/JAR/base archive và workload tương ứng |
| `classes.jsa` mặc định của JDK | Base CDS archive phân phối hoặc tạo từ runtime | Gắn với runtime/JDK; không chép tùy tiện từ JDK khác |
| `app.aot` trên JDK hiện đại | AOT cache mới, rộng hơn AppCDS truyền thống | **Tạo lại** nếu ứng dụng, JDK release hoặc OS/CPU architecture thay đổi |

Không nhầm `app.classlist` và `app.jsa`:

- Class list là **tập dữ liệu đầu vào** quan sát trong một lượt chạy.
- Archive là **sản phẩm đã xử lý** do JVM tạo từ class list và các class thực tế, có cấu trúc nội bộ liên quan đến runtime.
- Một dòng tên class có trong class list **không bảo đảm** lớp được archive thành công.
- Một class **không có trong archive** vẫn có thể được JVM nạp bình thường từ JAR khi ứng dụng cần, tùy tình huống và chế độ sharing.

Vì vậy, tạo lại archive là bước **tái tạo artifact tối ưu hóa**, không phải tạo bản sao thay thế `.jar` hoặc dữ liệu nghiệp vụ.

## 3. Vì sao thay đổi JDK phải tạo lại archive?

CDS archive chứa thông tin runtime đã tối ưu cho **bản dựng HotSpot/JDK cụ thể**. JVM của JDK khác có thể dùng layout và metadata của class, thư viện hoặc cơ chế nội bộ khác. Archive được sản xuất bởi build cũ không có bảo đảm tương thích bit-for-bit với build mới.

Những thay đổi nên được xem là **tín hiệu tái tạo**:

- Nâng Java feature release, ví dụ JDK 17 → 21 hoặc 21 → 25.
- Cập nhật bản vá JDK, ví dụ cùng nhánh 21 nhưng runtime build đã khác.
- Chuyển vendor/distribution, ví dụ một bộ JDK được thay bằng distribution khác.
- Thay JDK runtime image đã tạo bởi `jlink`.
- Chuyển hệ điều hành hoặc CPU architecture/container base image khi runtime thực tế thay đổi.
- Đổi những VM options quan trọng có ảnh hưởng tới archived class loading/linking.

JDK 25 `java` manual nêu rõ nội dung CDS archive **specific to each JDK build**. Đừng suy luận rằng `Runtime.version().feature()` giống nhau là đủ để sử dụng lại `.jsa`. Build ID, image và tính tương thích ở cấp VM mới là điều JVM kiểm tra.

### 3.1. Rebuild toàn bộ theo môi trường deploy

Mô hình an toàn:

~~~text
Source + dependencies
    |
    v
Chốt phiên bản JDK / runtime image
    |
    v
Đóng gói JAR/module
    |
    v
Chạy training trên đúng JDK + artifact
    |
    v
Tạo archive cho build đó
    |
    v
Kiểm tra -Xshare:on / log CDS
    |
    v
Gắn cả JAR và archive vào cùng release image
~~~

Nếu đổi JDK trong Dockerfile nhưng giữ nguyên tệp `app.jsa` từ image cũ, archive ấy là **artifact đáng ngờ**. Tạo lại bằng image JDK mới, xác minh strict, rồi mới promote release.

### 3.2. Đừng tạo archive bằng JDK phát triển khác JDK sản xuất

Ví dụ developer build trên JDK 24 nhưng server chạy JDK 21. File `.class` có thể đã được biên dịch `--release 17` và được cả hai runtime chạy đúng; điều đó **không làm archive của JDK 24 tương thích với JVM 21**.

Cần tách:

- **Class-file compatibility:** bytecode/API mà compiler phát ra, chịu ảnh hưởng `javac --release`.
- **Archive compatibility:** định dạng và thông tin nạp class do runtime/JDK tạo archive, gắn với VM build.

Chạy ứng dụng được trên hai JDK **không đồng nghĩa dùng chung archive**.

## 4. Vì sao thay đổi JAR hoặc những đầu vào đã lưu phải tạo lại?

Khi tạo AppCDS, JVM gắn archive với những **JAR/classpath/module path** cần thiết. Nếu một JAR trong classpath/module path được **sửa đổi sau thời điểm archive tạo**, tài liệu `java` hiện hành quy định archive **không được nạp** như cũ.

Các nguyên nhân thường gặp:

- Rebuild `app.jar` sau khi sửa code.
- Nâng một dependency JAR, kể cả khi tên file trên classpath giữ nguyên.
- Thay class, resource hoặc manifest trong JAR làm artifact khác.
- Thay JAR trong một container image mà quên cập nhật archive đã đóng gói.
- Di chuyển/thay đổi cách sắp xếp classpath không còn thỏa điều kiện tại thời điểm dump.
- Thay cách chạy module, module-related flags hoặc module path gây mất tương thích.

**Không kiểm tra chỉ theo tên tệp.** Hai artifact đều tên `app.jar` nhưng có nội dung khác; archive của bản thứ nhất không thể tự động được coi là hợp lệ cho bản thứ hai. Tương tự, chỉ dựa vào số version ở filename không chứng minh byte JAR là như cũ.

### 4.1. Những dấu hiệu JAR mismatch trong log

Ở một bài kiểm thử trên JDK 24, sau khi thay `app.jar` v1 bằng JAR v2 có class được sửa, JVM chạy `-Xshare:on` với archive cũ trả exit code **1** và chẩn đoán có nội dung:

~~~text
app.jar timestamp has changed.
app.jar size has changed.
Unable to map shared spaces
Unable to use shared archive.
~~~

Đây là **những trích đoạn thông báo quan sát được**, không phải stdout ổn định cho mọi OS/JDK. Đường dẫn và định dạng log thay đổi theo phiên bản. Trong triển khai thật, các thông báo có thể khác hoặc thể hiện dạng mismatch khác; ý nghĩa chung là JVM **không sử dụng được archive**.

### 4.2. Một đầu vào không làm JAR đổi nhưng làm workload đổi

Ví dụ:

- Cấu hình bật thêm một plugin/feature flag.
- Thay phần cấu hình DI, profile Spring hoặc cách nạp resource.
- Thêm endpoint sẽ được gọi trong giai đoạn startup/readiness.
- Đổi thứ tự khởi động, giới hạn module/agent hoặc cách tạo class động.

Nếu **không chạm tới classpath/JDK** và archive vẫn được chấp nhận, nó có thể **vẫn hợp lệ**, nhưng nhiều class phát sinh trong profile mới không được lưu. Khi đó, cần cân nhắc **tạo lại từ workload đại diện** để cập nhật tập class và đo lợi ích. Đây là vấn đề **coverage/performance**, không nhất thiết là lỗi bắt buộc của JVM.

**Phân biệt hai câu hỏi:**

1. Archive có **được JVM chấp nhận** không?
2. Archive có **đủ class có ích** để tối ưu đường chạy mới không?

Không dùng kết quả “không báo lỗi” để trả lời thay câu hỏi thứ hai.

## 5. Bảng quyết định: thay đổi nào cần tạo lại?

| Thay đổi | Rủi ro đối với archive | Hành động |
| --- | --- | --- |
| JDK build/patch/vendor thay đổi | Không tương thích archive | Tạo lại archive trên JDK đích |
| Runtime image `jlink` đổi | Metadata/JDK image có thể khác | Tạo lại với image mới |
| Class hoặc resource JAR thay đổi | JAR validation mismatch | Tạo lại class list/archiving cho artifact mới |
| Dependency JAR nâng phiên bản | Đầu vào lưu trữ thay đổi | Tạo lại archive, kiểm tra classpath |
| Thêm/bớt/sắp lại classpath | Có thể vi phạm điều kiện dump/runtime | Kiểm tra ràng buộc, tạo lại khi không tương thích |
| Đổi module path/module flags | Có thể làm mất toàn bộ hoặc một phần tối ưu | Giữ cấu hình nhất quán, tái tạo nếu cần |
| Dynamic archive dùng base archive mới | Top-layer gắn với base tương thích | Tái tạo dynamic overlay cho base mới |
| Thay CPU/OS/container runtime | Không mặc định portable | Xây mới trên nền tảng đích |
| Đổi profile/feature flag nhưng JAR không đổi | Có thể bỏ sót class của workload mới | Chạy training/benchmark lại khi đường startup đổi |
| Thay dữ liệu DB mà không tác động class loading | Thường không làm archive vô hiệu chỉ vì dữ liệu khác | Không rebuild chỉ do mọi bản ghi DB đổi; giám sát workload |
| Thay một biến môi trường chỉ ảnh hưởng text đầu ra | Có thể không ảnh hưởng tính hợp lệ CDS | Đánh giá tác động thực; không tuyên bố mọi env var buộc rebuild |
| Sửa quyền truy cập/archive bị thiếu hoặc hỏng | Archive không đọc được | Khôi phục/tạo lại artifact tin cậy và kiểm tra quyền |
| Đổi path JAR mà vẫn giữ byte, classpath order | Có thể ảnh hưởng archive validation và class loading | Kiểm chứng, ưu tiên ổn định đường dẫn trong image |
| Đổi JVM agent/instrumentation | Class bytes/VM constraints có thể khác | Test đúng bộ agent/runtime, rebuild nếu không dùng được |

**Quy tắc CI đơn giản:** Nếu build tạo ra một image ứng dụng/JDK mới, hãy coi archive là **build output của chính image đó**, thay vì lấy một tệp `.jsa` từ release trước rồi hy vọng còn hợp lệ.

## 6. Ví dụ Java 17+: tạo v1, dùng archive, sửa JAR, gặp lỗi, tạo lại

Bài thực hành tạo hai bản JAR **cùng đường dẫn** nhưng **khác bytecode**. Nó minh họa chính xác tình huống archive cần được tái tạo sau khi thay đổi đầu vào.

### 6.1. Mã nguồn hoàn chỉnh

Tạo `src/demo/App.java`:

~~~java
package demo;

public final class App {
    public static void main(String[] args) {
        System.out.println("APP=" + Greeting.value());
    }
}

final class Greeting {
    static String value() {
        return "v1";
    }
}
~~~

Đây là một file Java hợp lệ; compiler tạo `demo/App.class` và `demo/Greeting.class`. `Greeting` được load khi `App.main` gọi `Greeting.value()`, nên nó là class tốt để kiểm chứng archive.

**Không có code bên ngoài hoặc thư viện third-party**, chỉ dùng Java SE.

### 6.2. Biên dịch và đóng gói v1

Trên shell bash (Linux/macOS/Git Bash):

~~~bash
mkdir -p classes
javac --release 17 -d classes src/demo/App.java
jar --create --file app.jar --main-class demo.App -C classes .
java -cp app.jar demo.App
~~~

PowerShell trên Windows có thể tạo `classes` bằng `New-Item -ItemType Directory -Path classes`, và dùng ba lệnh `javac`/`jar`/`java` giống nhau.

Stdout:

~~~text
APP=v1
~~~

Lệnh `javac --release 17` bảo đảm ví dụ dùng API và class format Java 17; **JVM đang tạo archive vẫn là phiên bản JDK được gọi bởi lệnh `java`**.

### 6.3. Tạo class list từ v1

~~~bash
java -Xshare:off \
  -XX:DumpLoadedClassList=app.classlist \
  -cp app.jar demo.App
~~~

Stdout:

~~~text
APP=v1
~~~

`app.classlist` chứa tên những class được nạp ở lượt chạy đó (gồm class JDK); riêng `demo/App` và `demo/Greeting` nằm trong danh sách của ví dụ.

Một số kiến thức về option:

- `-Xshare:off`: không dùng archive CDS trong lượt thu class list, để tạo dữ liệu quan sát.
- `-XX:DumpLoadedClassList=app.classlist`: ghi danh sách class load.
- `-cp app.jar`: dùng JAR ứng dụng đã đóng gói.
- `demo.App`: chạy chính ứng dụng để phát sinh đường load thật.

Không tự viết danh sách `jar tf app.jar` rồi coi mọi class trong JAR đều đã sử dụng. AppCDS chọn theo những lớp được load trong workload thực tế và đủ điều kiện.

### 6.4. Dump static archive của v1

~~~bash
java -Xshare:dump \
  -XX:SharedArchiveFile=app.jsa \
  -XX:SharedClassListFile=app.classlist \
  -cp app.jar
~~~

Khi thành công, `app.jsa` là archive static tạo từ JDK và artifact v1. `app.classlist` là input của quá trình dump; **archive chưa phải một phần tự tạo ra khi chỉ chạy `javac` hoặc `jar`**.

**Điều kiện quan trọng trong tài liệu JDK hiện hành:** khi dùng quy trình này, classpath cho bước tạo archive cần dùng **JAR**, không phải thư mục class không rỗng dạng `-cp classes`. Các điều kiện module path/classpath cụ thể được Javadoc `java` mô tả.

### 6.5. Chạy v1 bằng archive và xác minh class share

~~~bash
java -Xshare:on \
  -XX:SharedArchiveFile=app.jsa \
  -Xlog:class+load=info \
  -cp app.jar demo.App
~~~

Trong output, tìm đoạn có nghĩa:

~~~text
demo.Greeting source: shared objects file
APP=v1
~~~

Log của HotSpot thực tế có timestamp/level/tag và rất nhiều dòng class load; hai dòng trên là **trích đoạn lược bớt metadata**, không phải cam kết hai dòng đứng cạnh nhau. Khi chạy thử trên JDK 24, `Greeting` được nạp từ `shared objects file` và ứng dụng in `APP=v1`.

- `APP=v1` chứng minh **kết quả ứng dụng**.
- `source: shared objects file` chứng minh **class đó được chia sẻ từ CDS**.
- `-Xshare:on` giúp test **fail-fast** nếu archive không sử dụng được, thay vì im lặng chạy đường khác.

### 6.6. Sửa đầu vào: tạo v2 nhưng giữ tên app.jar

Trong `src/demo/App.java`, chỉ sửa:

~~~java
final class Greeting {
    static String value() {
        return "v2-CHANGED";
    }
}
~~~

Đây là **đoạn thay thế class `Greeting` trong file đã có**, không phải file Java độc lập. Giữ `demo.App` và phần còn lại nguyên như `v1`.

Biên dịch lại và **thay JAR cũ bằng JAR v2**:

~~~bash
javac --release 17 -d classes src/demo/App.java
rm -f app.jar
jar --create --file app.jar --main-class demo.App -C classes .
java -cp app.jar demo.App
~~~

PowerShell Windows dùng:

~~~powershell
javac --release 17 -d classes src/demo/App.java
Remove-Item -LiteralPath app.jar
jar --create --file app.jar --main-class demo.App -C classes .
java -cp app.jar demo.App
~~~

Stdout:

~~~text
APP=v2-CHANGED
~~~

**Đây là thao tác của thư mục demo/bản build**, tuyệt đối không chạy `rm app.jar` trên artifact production nếu chưa có release pipeline bảo đảm backup/rollback.

### 6.7. Cố dùng archive v1 với JAR v2

~~~bash
java -Xshare:on \
  -XX:SharedArchiveFile=app.jsa \
  -Xlog:cds=info \
  -cp app.jar demo.App
~~~

Kết quả trong thử nghiệm JDK 24:

- **Exit code: 1**, JVM không chạy `main`.
- Có cảnh báo `app.jar timestamp has changed` và `app.jar size has changed`.
- JVM báo `Unable to map shared spaces` / `Unable to use shared archive`.

Không sao chép **một message cố định** làm điều kiện nhận diện duy nhất: các phiên bản JDK, OS, kiểu mismatch và phương pháp archive khác nhau có thể có log khác. Điều phải kiểm là **exit status** và **trạng thái sử dụng archive thực tế**.

### 6.8. Chế độ fallback `-Xshare:auto`

~~~bash
java -Xshare:auto \
  -XX:SharedArchiveFile=app.jsa \
  -cp app.jar demo.App
~~~

Trong thử nghiệm, JVM bỏ qua archive không phù hợp và **chạy ứng dụng thành công**:

~~~text
APP=v2-CHANGED
~~~

**Đừng hiểu sai:** `APP=v2-CHANGED` chứng minh chương trình hoạt động đúng, nhưng **không chứng minh archive cũ đã được dùng**. Chế độ `auto` có thể fallback nên ứng dụng không báo lỗi dù mất lợi ích CDS từ archive chỉ định.

Vì vậy, trong CI dùng `-Xshare:on` và log class load để phát hiện archive stale. Trong production cân nhắc `auto` nếu ưu tiên tính sẵn sàng hơn việc phải sử dụng archive bằng mọi giá, đồng thời **giám sát fallback**.

### 6.9. Tạo lại class list/archive cho v2

~~~bash
java -Xshare:off \
  -XX:DumpLoadedClassList=app-v2.classlist \
  -cp app.jar demo.App

java -Xshare:dump \
  -XX:SharedArchiveFile=app-v2.jsa \
  -XX:SharedClassListFile=app-v2.classlist \
  -cp app.jar

java -Xshare:on \
  -XX:SharedArchiveFile=app-v2.jsa \
  -Xlog:class+load=info \
  -cp app.jar demo.App
~~~

Kết quả v2:

~~~text
APP=v2-CHANGED
~~~

Và log cho `demo.Greeting` lại thể hiện `source: shared objects file`. Trong thử nghiệm JDK 24, ba giai đoạn chạy thành công sau khi tạo archive mới.

**Quy trình tái tạo đã hoàn tất:** compile/build JAR v2 → thu lại class list → dump archive v2 → kiểm tra strict và xác minh class được share.

## 7. Ba kết quả kiểm thử phải được tách riêng

| Trường hợp | Dùng archive? | Ứng dụng chạy? | Kết luận |
| --- | --- | --- | --- |
| v1 JAR + v1 archive, `-Xshare:on` | Có, `Greeting` shared | Có, `APP=v1` | Đúng artifact |
| v2 JAR + v1 archive, `-Xshare:on` | Không, báo mismatch | Không, exit 1 | **Phải tạo lại** |
| v2 JAR + v1 archive, `-Xshare:auto` | Có thể fallback không dùng archive cũ | Có, `APP=v2-CHANGED` | Đúng chức năng nhưng chưa xác nhận tối ưu hóa |
| v2 JAR + v2 archive, `-Xshare:on` | Có, `Greeting` shared | Có, `APP=v2-CHANGED` | Tạo lại thành công |

Đây là kết quả cho **một JDK 24 HotSpot trên Windows** và một chương trình nhỏ. Đừng xem số exit code/chuỗi log tương ứng là contract portable cho mọi JVM implementation. Tài liệu chính thức quy định tính tương thích của archive; **triển khai cụ thể có thể trình bày lỗi khác**.

### 7.1. Kiểm thử JAR đổi không phải kiểm thử JDK đổi

Ví dụ trên thực sự **đổi JAR**, không đổi JDK. Chúng ta **không** tuyên bố đã mô phỏng việc dùng archive giữa hai JDK khác nhau trong cùng bài demo. Quy tắc **rebuild sau đổi JDK** được lấy từ tài liệu HotSpot/`java` hiện hành; test ở CI có thể dùng matrix JDK riêng nếu hệ thống triển khai nhiều runtime.

## 8. Khi nào cần thu lại class list, khi nào có thể chỉ dump?

Một cách phân biệt hữu ích:

### 8.1. Đổi JDK build

**Khuyến nghị:** build/training lại toàn bộ trong JDK đích. Về lý thuyết, một số danh sách class cũ có thể còn có tên phù hợp, nhưng JDK mới có thể load class chuẩn khác, thư viện nội bộ khác hoặc các class framework phát sinh khác trong startup. Thu lại class list qua lượt chạy đại diện sẽ phản ánh đúng runtime và giảm nguy cơ thiếu/điều kiện không tương thích.

### 8.2. Đổi JAR class hoặc dependency

**Khuyến nghị:** thu lại list và dump từ JAR mới. Một class được thêm vào đường startup có thể không có trong danh sách cũ; nếu chỉ dump list cũ, JVM không tự biết toàn bộ đường code mới nên có thể bỏ lỡ tối ưu hóa.

### 8.3. Chỉ đổi một flag log không ảnh hưởng class loading

Archive có thể vẫn dùng; không cần thiết bắt buộc rebuild **mọi khi** có một thay đổi không liên quan. Hãy kiểm tra strict run và log CDS, rồi quyết định dựa trên tác động thực.

### 8.4. Class list còn đúng nhưng archive mất/hỏng

Có thể tạo lại archive từ **cùng input còn hợp lệ** theo workflow hiện tại. Tuy nhiên, nếu thay JDK/JAR mà chỉ re-dump list cũ, chưa chắc tập class được chọn tối ưu hoặc chấp nhận; với release mới nên chạy lại training.

**Nguyên tắc ưu tiên tính tái lập hơn tiết kiệm bước:** với deployment artifact thay đổi, thu mới + dump mới thường đơn giản để bảo đảm khớp, hơn là điều tra xem danh sách lưu từ lần trước còn đủ điều kiện đến mức nào.

## 9. Static archive, dynamic archive và quan hệ với base

HotSpot hiện đại có hai cách thực hành AppCDS phổ biến.

### 9.1. Static archive từ class list

Ba bước minh họa trước:

~~~text
DumpLoadedClassList -> SharedClassListFile -> SharedArchiveFile
~~~

Static archive được tạo từ runtime/JDK/classpath của bước dump. Khi một đầu vào ấy đổi, cần kiểm tra và tạo lại; `app.classlist` cũng nên được thu lại nếu workload hoặc JDK thay đổi.

### 9.2. Dynamic archive khi chương trình thoát

Từ JDK 13, JEP 350 hỗ trợ:

~~~bash
java -XX:ArchiveClassesAtExit=app-dynamic.jsa \
  -cp app.jar demo.App
~~~

Sau khi JVM thoát bình thường và archive được tạo thành công:

~~~bash
java -XX:SharedArchiveFile=app-dynamic.jsa \
  -Xlog:class+load=info \
  -cp app.jar demo.App
~~~

Dynamic archive thường chứa phần lớp thêm vào so với **base CDS archive** mà runtime dùng khi training. Điều này tạo một **quan hệ phụ thuộc**: nếu base archive/JDK image thay đổi không tương thích, dynamic archive cũng phải được xem xét và thường **tạo lại**.

Không vì file dynamic `.jsa` nhỏ hơn static `.jsa` mà kết luận nó tương thích giữa mọi JDK build. Nó vẫn gắn với runtime và các đầu vào class loading.

### 9.3. Khi chỉ định hai archive

Một số cấu hình HotSpot dùng static base và dynamic top-layer:

~~~text
-XX:SharedArchiveFile=base.jsa:app-dynamic.jsa
~~~

Trên **Windows**, nếu truyền cả hai path trong một option, dấu ngăn cách thường dùng `;` thay vì `:`.

Tài liệu `java` giải thích dynamic archive lưu tham chiếu tới base archive khi tạo. Vì thế, **đổi base archive mà giữ nguyên dynamic overlay** có thể làm cấu hình không tương thích.

**Vận hành:** hãy xem cặp base/top-layer là một **bộ artifact có version đồng bộ**, không đổi độc lập một file mà không xác minh phần còn lại.

## 10. Tự động tạo lại archive: `-XX:+AutoCreateSharedArchive`

Ngoài cơ chế thủ công, tài liệu HotSpot hiện hành có lựa chọn:

~~~bash
java -XX:+AutoCreateSharedArchive \
  -XX:SharedArchiveFile=app-dynamic.jsa \
  -cp app.jar demo.App
~~~

Mục đích: JVM có thể dùng archive động nếu thích hợp, hoặc tạo ra archive khi kết thúc một lượt chạy mà chưa có archive. Điều này giảm thao tác class list và dump riêng.

**Quy tắc quan trọng theo JDK 25 manual:**

1. Nếu file archive tồn tại và được tạo bằng **cùng JDK build**, JVM có thể nạp nó.
2. Nếu file **chưa tồn tại**, JVM có thể tạo archive khi thoát.
3. Nếu file tồn tại nhưng được tạo bằng **JDK khác và archive đó được tạo từ JDK 19 trở lên**, JVM có thể **thay archive cũ bằng archive của JDK mới** khi thoát.
4. Nếu file được tạo bằng **JDK trước 19**, cơ chế này có giới hạn: tài liệu mô tả file đó bị bỏ qua, **không được nạp và cũng không được tự thay** chỉ vì option này.

Vì vậy, `AutoCreateSharedArchive` có thể hỗ trợ **tự phục hồi khi đổi JDK build** trong điều kiện được tài liệu nêu. Nó **không phải bảo đảm mọi thay đổi JAR, module, cấu hình hay archive hỏng đều được tự sửa đúng**. Với release pipeline, vẫn cần theo dõi archive thực được dùng và kiểm thử strict/tương thích sau khi build.

### 10.1. Dùng đúng nơi: flag này không tự biến static archive cũ thành archive mới

`AutoCreateSharedArchive` hướng tới việc tạo/dùng **dynamic archive** theo cơ chế của HotSpot. Nó **không** là lệnh “làm sạch mọi static `.jsa` được tạo với `-Xshare:dump`” hoặc công cụ thay thế các bước kiểm chứng ứng dụng.

Với ứng dụng có SLA startup khắt khe, nên thiết kế quá trình tạo archive/cache chủ động trong CI/CD, thay vì mong lần khởi động production tự làm tất cả bước train.

### 10.2. Cần coi việc ghi archive như thao tác artifact

Nếu nhiều tiến trình cùng cố tạo/ghi vào một path, phải tránh race và file chưa hoàn tất được dùng. Không coi một archive path shared writable là hệ thống cache phân tán có khóa tự động cho mọi quy trình triển khai.

Trong CI/CD, sinh archive ở workspace build riêng, xác minh, rồi publish/promote artifact nguyên vẹn cùng image. Nếu cần sinh lúc runtime, đảm bảo quyền ghi, phân quyền người tạo, lock/lifecycle và khả năng fallback được thiết kế rõ.

## 11. Những ràng buộc classpath và module path làm archive mất hiệu lực

Tài liệu `java` hiện hành liệt kê điều kiện cần lưu ý khi xây/dùng CDS archive:

- **Không dùng thư mục class không rỗng** trong classpath hoặc module path cho workflow archive yêu cầu JAR.
- Với `--module-path`, chỉ các **modular JAR** được hỗ trợ trong các tình huống tương ứng; không tự giả định exploded modules có thể archive.
- Classpath lúc tạo archive phải **bằng hoặc là prefix** của classpath lúc chạy trong những trường hợp được hỗ trợ.
- **JAR trong classpath/module path bị sửa đổi sau khi sinh archive** khiến archive không thể nạp.
- Các option module như `--module-path`, `--module`, `--add-modules`, `--enable-native-access` nếu có cần nhất quán giữa lúc tạo và lúc chạy; mismatch có thể làm một phần hoặc toàn bộ tối ưu hóa bị vô hiệu.
- Một số option module như `--upgrade-module-path`, `--patch-module` hoặc `--limit-modules` có các hạn chế/khả năng vô hiệu CDS được nêu trong tài liệu.

Không được suy từ câu “classpath runtime có thể mở rộng theo prefix” thành quyền **đổi thứ tự JAR tùy ý** hoặc thay một JAR trong prefix bằng nội dung khác. Thay đổi thứ tự có thể thay class được load trong Java, do đó còn có rủi ro **functional correctness**, không chỉ cache.

### 11.1. Ghi nhận cấu hình dump/runtime

Trong pipeline, nên lưu đủ thông tin để tái tạo:

~~~text
java vendor/version/build
OS/architecture
runtime image fingerprint
application jar hash
dependency jar hashes theo đúng thứ tự
classpath/module path
module-related launch options
agent/instrumentation options
profile/feature flags dùng ở training
archive type (static/dynamic/AOT)
training scenario và test output
~~~

Không cần mọi thông tin này nằm trong tên file `.jsa`. Có thể lưu thành **build manifest/provenance** riêng và sử dụng nó làm input cho key cache. Nhưng phải có đủ bằng chứng để biết archive đó thuộc **đúng release**.

### 11.2. Hash nào nên dùng?

Đối với artifact JAR/distro, có thể tính SHA-256 ở pipeline:

~~~bash
sha256sum app.jar
~~~

Trên PowerShell:

~~~powershell
(Get-FileHash -Algorithm SHA256 -Path app.jar).Hash
~~~

Đây là cách **quản trị artifact**, không phải thuật toán thay thế những validation nội bộ mà HotSpot áp dụng. Hai input JAR có cùng path nhưng SHA-256 khác là dấu hiệu rõ ràng đã đổi và nên tạo lại archive.

Lưu ý hash các dependency JAR theo thứ tự/path cần thiết, không chỉ hash `app.jar` nếu classpath gồm nhiều JAR.

## 12. Tạo lại archive trong CI/CD và Docker

Một pipeline có thể tổ chức:

~~~text
1. Resolve dependencies cố định, có lock/checksum
2. Chọn JDK toolchain + runtime image cụ thể
3. Build ứng dụng thành JAR/module
4. Chạy kiểm thử chức năng thường
5. Thu class list hoặc tạo dynamic archive qua workload an toàn
6. Kiểm thử JVM start với -Xshare:on và archive mới
7. Đọc log xác nhận class quan trọng đã shared
8. Benchmark startup (nếu đây là release performance-sensitive)
9. Đóng gói JAR + archive + manifest + runtime vào cùng image
10. Phát hành và giám sát fallback/latency sau triển khai
~~~

### 12.1. Cùng một image runtime

Nếu Docker multi-stage build tạo archive ở image builder khác runtime image, phải bảo đảm **JDK build và các ràng buộc nền tảng tương thích**. Cách dễ kiểm soát là tạo archive trong cùng runtime image hoặc một môi trường build sử dụng **đúng runtime bits** và artifact như production.

Không nên mount archive được sản xuất từ máy developer Windows để sử dụng tùy ý ở container Linux. Một bytecode JAR Java có thể portable hơn; CDS archive **không cùng mức portable**.

### 12.2. Immutable release artifact

Đừng chạy:

~~~text
deploy image v2 + keep volume app.jsa from v1
~~~

mà không kiểm tra phiên bản. Cách an toàn hơn:

~~~text
image v1: JDK build A + JAR sha X + archive sha P
image v2: JDK build B + JAR sha Y + archive sha Q
~~~

Nếu phần JDK/JAR không đổi nhưng chỉ cấu hình runtime đổi, cũng phải xác định liệu tập class/VM flags có khác không, rồi kiểm chứng. Không đặt logic bất biến dựa trên “tên image tag giống nhau” vì tag có thể được repush với nội dung mới.

### 12.3. Không đưa training dữ liệu thật hoặc secret vào artifact

Archive/CDS chứa thông tin nạp lớp, không phải snapshot dữ liệu DB của ứng dụng. Tuy nhiên, quy trình training có thể đọc config, chạm service và tạo log. Hãy dùng môi trường cô lập, request/test fixture an toàn, tránh để secret trong lệnh, artifact hoặc log. Không thực hiện giao dịch tài chính hay thay đổi dữ liệu production chỉ để làm nóng các class.

### 12.4. Chuẩn bị rollback

Nếu release v2 phải rollback sang v1, dùng **đúng bộ JDK/JAR/archive của v1**, không lấy archive của v2 gắn vào binary v1. Tập artifact deploy nên được version hóa và khả năng rollback được thử như một đơn vị.

## 13. Chế độ kiểm chứng: `-Xshare:on`, `auto`, logging và exit code

### 13.1. `-Xshare:on` cho CI và điều tra

~~~bash
java -Xshare:on -XX:SharedArchiveFile=app.jsa -cp app.jar demo.App
~~~

Nếu archive không thể dùng, HotSpot có thể **fail fast**. Đây là cách hợp lý để kiểm tra một release artifact đã được tạo hợp lệ. Không đánh đồng chế độ strict với khuyến nghị **luôn buộc fail production**: nếu mục tiêu kinh doanh là duy trì availability dù mất cache, cần chính sách khác.

### 13.2. `-Xshare:auto` cho đường fallback

~~~bash
java -Xshare:auto -XX:SharedArchiveFile=app.jsa -cp app.jar demo.App
~~~

Khi archive không dùng được, ứng dụng có thể chạy không sử dụng archive tùy tình huống. Đó là **lợi thế availability**, nhưng có rủi ro hiệu năng chậm hơn và lỗi cache không được phát hiện nếu không theo dõi log.

### 13.3. `-Xlog:cds=info` để xem trạng thái archive

~~~bash
java -Xlog:cds=info \
  -XX:SharedArchiveFile=app.jsa \
  -cp app.jar demo.App
~~~

Log CDS giúp phân biệt archive có được map, có bị bỏ qua, không tương thích hoặc có lỗi khác. Dùng mức độ log có kiểm soát; không bật `debug/trace` ở production mặc định khi không cần.

### 13.4. `-Xlog:class+load=info` để chứng minh lớp đã được share

~~~bash
java -Xlog:class+load=info \
  -XX:SharedArchiveFile=app.jsa \
  -cp app.jar demo.App
~~~

Kiểm tra lớp quan trọng, ví dụ:

~~~text
demo.Greeting source: shared objects file
~~~

Một class được load từ JAR không phải bằng chứng chia sẻ archive cho class đó. Ngược lại, class không shared không nhất thiết là application failure; có thể nó không được chọn/không đủ điều kiện/cần nạp thường.

## 14. Điểm mới cần biết nếu triển khai JDK 24/25+: AOT cache

**Special Note yêu cầu kiến thức còn áp dụng**, nên không nên dừng tại thao tác AppCDS thủ công của Java 10. JDK 24 có **Ahead-of-Time Class Loading & Linking** (JEP 483) và JDK 25 có **Ahead-of-Time Command-Line Ergonomics** (JEP 514).

AOT cache có thể chứa thêm artifact tối ưu hóa ngoài cách chia sẻ class truyền thống. Theo `java` manual JDK 25, cache gắn với tổ hợp:

- Một **application cụ thể** (classpath, `-jar` hoặc module path).
- Một **JDK release cụ thể**.
- Một **OS và CPU architecture cụ thể**.

**Nếu một trong những yếu tố ấy thay đổi thì phải tạo lại AOT cache.** Đây là quy tắc được tài liệu chính thức phát biểu rõ.

### 14.1. Cách dùng đơn giản trên JDK 25+

Với một ứng dụng `app.jar`:

~~~bash
java -XX:AOTCacheOutput=app.aot -cp app.jar demo.App
java -XX:AOTCache=app.aot -cp app.jar demo.App
~~~

Lệnh đầu là một workflow đơn giản để train/tạo AOT cache; lệnh sau chạy ứng dụng với cache. **Không dùng nguyên các flag này cho JDK 17:** phần JDK 25 phải được chạy bằng runtime đã hỗ trợ.

Có thể kiểm tra tình trạng AOT bằng:

~~~bash
java -XX:AOTCache=app.aot -Xlog:aot -cp app.jar demo.App
~~~

Khi muốn kiểm tra **fail-fast** trong một môi trường test được kiểm soát, JDK manual mô tả chế độ `-XX:AOTMode=required`; trong production, chế độ mặc định/auto giúp giảm rủi ro crash do AOT cache không dùng được, nhưng cần giám sát.

### 14.2. Không trộn cache `.aot` với archive `.jsa`

| Nội dung | AppCDS `.jsa` | AOT cache `.aot` |
| --- | --- | --- |
| Mục đích | Chia sẻ dữ liệu class, hỗ trợ startup/footprint | Có thể lưu nhiều artifact tối ưu hóa AOT hơn |
| Cấu hình điển hình | `-XX:SharedArchiveFile=...` | `-XX:AOTCache=...` |
| Tạo thủ công | `-Xshare:dump` / `ArchiveClassesAtExit` | `-XX:AOTCacheOutput=...` trên JDK 25+ |
| Tính tương thích | Gắn với JDK/JAR/module và VM constraints | Gắn với application/JDK/OS/CPU, cùng constraints theo JDK |
| Thay đổi đầu vào | Cần đánh giá và thường tạo lại | Tạo lại khi tổ hợp đầu vào mà manual định nghĩa thay đổi |
| Kiểm chứng | `-Xlog:cds`, `-Xlog:class+load` | `-Xlog:aot` và kiểm tra mode/latency |

Không đổi đuôi một file từ `.jsa` sang `.aot` rồi dùng flag tương ứng: đây là **hai artifact format/workflow khác nhau**. Mỗi loại phải được tạo bởi JVM với đúng option và runtime.

### 14.3. So sánh theo mục tiêu thay vì chạy mọi cơ chế cùng lúc

Nếu đang vận hành ứng dụng trên JDK 17/21, AppCDS static/dynamic vẫn là lựa chọn hợp lệ. Nếu nâng sang JDK 25+, nên đánh giá AOT cache và cách build mới, không mặc định tài liệu của Java 10 luôn là workflow tốt nhất.

Điểm không thay đổi: **đầu vào build phải khớp**, workload training phải đại diện, artifact phải được xác minh và đo hiệu quả trước khi coi là cải tiến.

## 15. Đầu vào nào cần có trong cache key của build pipeline?

Một bảng metadata khuyến nghị:

| Thành phần | Ví dụ | Vì sao đưa vào? |
| --- | --- | --- |
| JDK build/vendor | `java -XshowSettings:properties -version`, image digest | Archive không portable giữa mọi JDK build |
| OS/architecture | Linux x86_64, Windows x64 | AOT/CDS data phụ thuộc nền tảng |
| JAR hash | SHA-256 của `app.jar` | Phát hiện class/resource bị thay |
| Dependency hashes | SHA-256 + thứ tự đường dẫn | Class loading phụ thuộc nội dung/order |
| JVM startup options | classpath, module flags, agents | Có thể ảnh hưởng điều kiện tương thích |
| Runtime image digest | Digest image/container | Theo dõi chính xác JDK/runtime bits |
| Training scenario version | `startup-smoke-v3` | Coverage class load có thể đổi |
| Archive builder | Static/dynamic/AOT + cờ tạo | Phân biệt các workflow |
| Validation status | strict launch, class shared, bench result | Không publish artifact lỗi |
| Artifact digest | SHA-256 của `app.jsa`/`app.aot` | Kiểm tra artifact đã publish không bị thay |

Đây là **cache-key/provenance cho CI**, không phải các trường mà HotSpot bắt buộc đọc từ một manifest do bạn viết. Bạn có thể tính hash của một biểu diễn chuẩn hóa (canonical) của metadata để quyết định tạo mới hay reuse, nhưng đừng tin chỉ một hash đầu vào nếu đã bỏ sót dependencies hoặc VM flags có ý nghĩa.

**Khuyến nghị mặc định:** nếu hệ thống deployment đổi thường xuyên, tạo archive cùng image mới thường đơn giản và đáng tin hơn dùng lại artifact qua nhiều image có trạng thái không rõ.

## 16. Phân biệt ba dạng “stale”

### 16.1. Stale không tương thích (*hard invalidation*)

JDK mới không nạp được `.jsa` cũ, hoặc JAR trên classpath đã bị sửa. Trong strict mode có thể **exit nonzero**.

**Hành động:** tạo lại archive đúng JDK/JAR/launch config, kiểm chứng rồi deploy.

### 16.2. Stale về phạm vi lớp (*coverage drift*)

JDK vẫn nạp archive, nhưng ứng dụng mới kích hoạt nhiều class chỉ load sau first request hoặc nhánh startup mới. Không có lỗi nội dung, nhưng lợi ích tối ưu hóa có thể thấp.

**Hành động:** xem class-load logs, bổ sung workload training hợp lý, tạo lại archive, đo startup/first-request.

### 16.3. Stale về hiệu năng (*performance regression*)

Archive nạp đúng và coverage vẫn hợp lý, nhưng tổng startup không cải thiện do thay CPU/memory, JDK collector, container storage, hệ thống đọc DB hoặc các yếu tố khác.

**Hành động:** benchmark A/B và profiling; không mặc định chỉ cần thêm class vào archive là giải quyết.

### 16.4. Stale về bảo mật/quyền truy cập

Artifact archive bị thay ngoài quy trình build, không được tin cậy về provenance hoặc có quyền ghi quá rộng.

**Hành động:** khôi phục artifact từ nguồn build đáng tin cậy, kiểm soát quyền, bổ sung signing/digest và kiểm tra phù hợp. `-XX:+VerifySharedSpaces` có thể kiểm tra CRC32 để phát hiện một số hỏng dữ liệu vô tình, **không thay thế cơ chế chống tampering có chủ đích hoặc bảo đảm xuất xứ**.

## 17. Những lỗi thường gặp và hướng xử lý

| Triệu chứng | Nguyên nhân khả dĩ | Cách làm |
| --- | --- | --- |
| `Unable to use shared archive` | JDK/JAR/archive không tương thích | Đọc CDS log, tạo lại với đúng inputs |
| `app.jar timestamp has changed` | File JAR khác thời điểm dump | So artifact, tạo lại archive |
| `app.jar size has changed` | Nội dung/packaging JAR thay đổi | Rebuild đúng JAR và verify |
| Strict `-Xshare:on` bị exit | Archive không được VM chấp nhận | Kiểm tra logs, JDK và classpath |
| `-Xshare:auto` vẫn chạy nhưng startup chậm hơn | Fallback bỏ qua archive | Theo dõi CDS logs, tạo lại |
| Không thấy `source: shared objects file` | Class không archived/không shared | Kiểm tra classlist/training/eligibility |
| Dynamic archive không nạp sau đổi base | Top-layer không khớp base archive/JDK | Tái tạo cả bộ base/top-layer |
| Thay module-related flags làm tối ưu giảm | Archived module graph bị vô hiệu một phần | Đồng nhất flags và kiểm chứng |
| Upgrade JDK nhưng giữ Docker volume `.jsa` | Artifact cũ gắn JDK build khác | Version hóa archive theo image |
| Thêm plugin nhưng archive vẫn chạy | Có thể chỉ là coverage drift | Train lại nếu startup/first-use có tác động |
| AOT `.aot` từ OS/arch khác | Không tương thích với runtime | Build trên đúng OS/CPU/runtime |
| Bật strict mode trên prod rồi gặp mismatch | Fail-fast khiến app không khởi động | Chọn fallback policy phù hợp, fix release pipeline |
| Chỉ đo kích thước `.jsa` | Không đo hiệu quả thực | Benchmark startup, p95 và footprint |
| Archive tạo từ JAR directory classpath | Không thỏa một số ràng buộc AppCDS | Package JAR và dùng classpath phù hợp |

**Không “sửa” mismatch bằng cách xóa cảnh báo khỏi log.** Phải sửa **tính nhất quán giữa archive và các đầu vào** hoặc chủ động bỏ sử dụng archive có vấn đề.

## 18. Câu hỏi và bài tập có đáp án

### Bài 1 — Đổi bản vá JDK

Bạn tạo `app.jsa` với một JDK build, hôm sau cập nhật sang JDK build khác cùng feature release. Dùng lại archive có được mặc định không?

**Đáp án:** Không. CDS archive gắn với JDK build; tạo lại và kiểm tra strict trên runtime mới.

### Bài 2 — Cùng tên JAR, khác byte

Cả hai release đều có `app.jar`, nhưng SHA-256 khác nhau. Archive cũ có chắc hợp lệ?

**Đáp án:** Không. Thay JAR có thể làm validation mismatch; tạo lại từ JAR mới. Tên/path giống nhau không chứng minh nội dung khớp.

### Bài 3 — Thay một database record

Bạn thay dữ liệu DB, JDK/JAR/classpath không đổi và đường class loading không thay. Có bắt buộc rebuild archive vì mọi dữ liệu DB đã khác?

**Đáp án:** Không chỉ vì một bản ghi DB đổi. AppCDS lưu dữ liệu class, không lưu tùy ý toàn bộ business data. Xem workload có thay đổi việc load class không.

### Bài 4 — `-Xshare:auto` vẫn chạy

Archive cũ không khớp JAR, nhưng ứng dụng in đúng `APP=v2-CHANGED` dưới `-Xshare:auto`. Điều này có chứng minh AppCDS được dùng không?

**Đáp án:** Không. JVM có thể fallback không sử dụng archive cũ. Cần xem log CDS/class load, hoặc strict test.

### Bài 5 — Kiểm tra sharing

Một service in đúng kết quả; log có `demo.Greeting source: shared objects file`. Kết luận gì?

**Đáp án:** Class `demo.Greeting` thực sự được nạp từ archive trong run đó; vẫn phải đo hiệu năng để biết lợi ích thực tế.

### Bài 6 — Classlist từ phiên bản cũ

Build v2 có class startup mới, nhưng CI vẫn lấy `app.classlist` từ v1 để dump. Rủi ro?

**Đáp án:** Có thể bỏ sót class mới hoặc điều kiện không khớp. Thu lại classlist từ workload v2 trong đúng runtime trước khi dump.

### Bài 7 — Archive động và base

Bạn thay base CDS archive mà giữ nguyên dynamic top-layer. Cần làm gì?

**Đáp án:** Coi hai artifact là một bộ tương thích; tạo lại dynamic archive (và base nếu cần) theo runtime mới, kiểm thử sử dụng thực.

### Bài 8 — Vì sao kiểm tra hash JAR?

**Đáp án:** Hash giúp nhận biết artifact bị đổi dù tên giữ nguyên; nhưng chỉ hash JAR chính chưa đủ nếu classpath còn nhiều dependency JAR/module khác.

### Bài 9 — Dùng JDK khác để build archive

Ứng dụng compile `--release 17`, archive tạo trên JDK 24, runtime chạy JDK 21. Có thể dùng chung archive JDK24 cho JDK21 không?

**Đáp án:** Không mặc định. Class-file compatibility và archive compatibility là hai việc khác; tạo archive với JDK/runtime đích.

### Bài 10 — Flag `AutoCreateSharedArchive`

Cờ này có thể tự tái tạo archive trong trường hợp nào theo tài liệu JDK hiện hành?

**Đáp án:** Có thể tạo file nếu chưa có, và có thể thay archive dynamic từ **JDK 19+** khi chuyển sang JDK build khác. Nó không bảo đảm tự sửa mọi mismatch JAR/module và không phải trình tạo lại static archive chung.

### Bài 11 — Đổi một feature flag

Một feature flag làm server bắt đầu tải thêm một provider vào startup; JVM vẫn dùng archive cũ không lỗi. Tình trạng gì?

**Đáp án:** Có thể là **coverage drift**. Đo first-use/startup và thu training mới nếu lớp mới nằm trên critical path.

### Bài 12 — Quyết định fallback

Nên đặt `-Xshare:on` trên mọi JVM production không?

**Đáp án:** Không có câu trả lời chung. Strict mode hữu ích cho CI/fail-fast; production có thể chọn `auto` để ứng dụng vẫn chạy nếu archive không dùng được, kèm giám sát. Quyết định theo availability và yêu cầu tối ưu.

### Bài 13 — AOT cache JDK 25

AOT cache được tạo trên Linux x64 với một JDK release, rồi mang sang OS/architecture khác. Có cần tạo lại?

**Đáp án:** Có. Tài liệu JDK 25 định nghĩa cache gắn với application, JDK release và OS/CPU architecture.

### Bài 14 — Dữ liệu đầu vào production

Muốn nạp thêm class bằng cách gọi mọi endpoint và ghi dữ liệu thanh toán thật trong training, có nên không?

**Đáp án:** Không. Dùng request đại diện an toàn và môi trường training/staging; archive là tối ưu hóa, không phải lý do chạy giao dịch nguy hiểm.

### Bài 15 — Rollback

Sau khi rollback JAR v2 → v1 nhưng giữ archive v2 vì file vẫn tồn tại, điều gì có thể xảy ra?

**Đáp án:** Archive có thể bị từ chối do JAR không khớp. Version hóa và rollback **cả bộ** JDK/JAR/archive theo release.

### Bài 16 — Archive được load nhưng startup không tốt

`-Xlog:cds` báo archive được map, một số class shared, nhưng startup chỉ cải thiện rất ít. Có nên tự động tăng số class không?

**Đáp án:** Chưa. Xác định bottleneck, benchmark nhiều lần, kiểm tra workload và chi phí I/O/DB/network trước khi mở rộng archive.

### Bài 17 — Cách phát hiện regression

Bạn muốn build pipeline không publish archive bị sai. Cần hai bước kiểm chứng tối thiểu nào?

**Đáp án:** Chạy ứng dụng bằng archive với strict sharing (`-Xshare:on`) để phát hiện mismatch và kiểm tra `-Xlog:class+load=info` cho những class quan trọng từ `shared objects file`. Có thể bổ sung benchmark/health test.

### Bài 18 — Xác định ai tạo archive

Một tệp `app.jsa` xuất hiện trong build output nhưng không có thông tin JDK/dependency/command. Có nên dùng ngay cho release mới?

**Đáp án:** Không nên. Thiếu provenance khiến không biết archive có khớp runtime không. Tạo lại bằng build pipeline có manifest và kiểm thử, sau đó publish.

## 19. Checklist triển khai thực tế

- [ ] Đã phân biệt **archive compatibility** và **coverage/performance** chưa?
- [ ] Có biết chính xác JDK build/vendor/runtime image dùng để sinh archive không?
- [ ] Có tạo lại archive khi nâng JDK, đổi vendor hoặc thay runtime image không?
- [ ] Có tạo lại archive khi JAR hoặc dependency JAR bị sửa không?
- [ ] Có hash các JAR/module inputs theo đúng classpath order không?
- [ ] Có chốt các module-related JVM options phù hợp với lúc dump không?
- [ ] Có hiểu ràng buộc classpath creation giống hoặc là prefix của classpath runtime không?
- [ ] Có tránh đưa thư mục class không rỗng vào workflow AppCDS chỉ hỗ trợ JAR không?
- [ ] Có giữ classlist và archive phù hợp với workload và JDK mới không?
- [ ] Nếu dùng dynamic archive, có gắn nó với đúng base archive của runtime không?
- [ ] Có dùng `-Xshare:on` trong CI để phát hiện archive không dùng được không?
- [ ] Có đọc `-Xlog:cds` và `-Xlog:class+load` để phân biệt fallback với shared thật không?
- [ ] Có đo startup/first-response trước và sau tạo lại archive không?
- [ ] Có hiểu rằng `-Xshare:auto` có thể giúp availability nhưng không chứng minh sharing không?
- [ ] Có biết điều kiện giới hạn của `-XX:+AutoCreateSharedArchive` với archive từ trước JDK 19 không?
- [ ] Có coi `.jsa` là output được version hóa cùng JAR/JDK/image không?
- [ ] Có kiểm soát ai được ghi/xóa/tạo archive và hash artifact đã publish không?
- [ ] Có giữ tùy chọn rollback JDK/JAR/archive như một bộ thống nhất không?
- [ ] Có tránh dùng dữ liệu thật hoặc secret trong workload training không?
- [ ] Nếu chạy JDK 25+, có xem AOT cache mới và ràng buộc recreate của nó không?
- [ ] Có test lại archive khi profile/feature flag gây thay đổi class loading không?
- [ ] Có tránh kết luận “CDS đang hiệu quả” chỉ vì ứng dụng chạy đúng không?

## 20. Tài liệu chính thức còn áp dụng

- [JDK 25 `java` Command — Application Class Data Sharing](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html#application-class-data-sharing): cách tạo static/dynamic AppCDS, classpath/JAR restrictions, `SharedArchiveFile` và chẩn đoán.
- [JDK 25 `java` Command — AutoCreateSharedArchive](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html#creating-dynamic-cds-archive-file-with-xxautocreatesharedarchive): quy tắc tự tạo/thay archive khi đổi JDK, giới hạn archive tạo trước JDK 19.
- [JDK 25 `java` Command — Restrictions on Class Path and Module Path](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html#restrictions-on-class-path-and-module-path): yêu cầu JAR không đổi, classpath prefix và các option module.
- [JDK 17 `java` Command — Application Class Data Sharing](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html#application-class-data-sharing): workflow AppCDS vẫn phù hợp cho mã chạy trên Java 17+.
- [JEP 310 — Application Class-Data Sharing](https://openjdk.org/jeps/310): tính năng AppCDS đưa vào Java 10.
- [JEP 350 — Dynamic CDS Archives](https://openjdk.org/jeps/350): cách tạo dynamic archive qua `ArchiveClassesAtExit` trên JDK 13+.
- [JEP 483 — Ahead-of-Time Class Loading & Linking](https://openjdk.org/jeps/483): AOT cache được bổ sung từ JDK 24.
- [JEP 514 — Ahead-of-Time Command-Line Ergonomics](https://openjdk.org/jeps/514): tạo/dùng AOT cache thuận tiện hơn từ JDK 25.
- [JDK 25 `java` Command — Ahead-of-Time Cache](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html#ahead-of-time-cache): AOT cache gắn với application/JDK/OS/CPU, `-XX:AOTCacheOutput` và `-XX:AOTCache`.
- [JDK 25 `java` Command — `-XX:+VerifySharedSpaces`](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): kiểm tra CRC32 đối với hư hỏng vô tình, không thay thế bảo vệ nguồn artifact.

**Tóm lại:** Một AppCDS archive được tạo từ **một tập class/JAR và một JDK/runtime build cụ thể**. Sau khi thay **JDK hoặc đầu vào đã lưu trong archive**, phải tạo lại artifact phù hợp và xác minh bằng strict startup/class-load logs. Đổi cấu hình có thể không gây lỗi tương thích nhưng vẫn làm archive thiếu class mới hữu ích cho startup — lúc đó cần retrain nếu benchmark cho thấy lợi ích. Với ứng dụng hiện đại, coi `.jsa` hoặc `.aot` là **artifact phiên bản hóa cùng JDK, JAR, dependencies và image**; đừng dùng sự thành công của fallback làm bằng chứng archive cũ vẫn hoạt động.