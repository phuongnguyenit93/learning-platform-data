# Kiểm tra ma trận JDK biên dịch và môi trường Java đích

Một ứng dụng Java **biên dịch thành công** trên JDK mới chưa chắc **chạy được** trên môi trường Java cũ. Ngược lại, dùng `javac --release` để tạo bytecode cũ hơn cũng **không tự đảm bảo** rằng mọi thư viện, annotation processor, tính năng runtime hay cấu hình triển khai đều tương thích. Khi phát hành phần mềm, cần kiểm tra đồng thời **JDK dùng để build**, **Java release mà compiler nhắm tới**, **API được gọi**, **class file của mọi dependency**, và **các Java runtime sẽ chạy ứng dụng**.

Bài Knowledge này trình bày cách lập và kiểm chứng **ma trận tương thích JDK biên dịch – Java đích** từ đơn giản đến CI nhiều phiên bản, kèm ví dụ Java 17+, lệnh `javac`/`java`, cách đọc class-file version, các trường hợp lỗi và checklist phát hành. Trọng tâm là **tính tương thích có bằng chứng**, không phải chỉ sửa một con số `target` rồi coi như đã hỗ trợ Java cũ.

## 1. Tách bốn khái niệm trước khi lập ma trận

**JDK biên dịch (build JDK)** là bộ công cụ thực sự chạy lệnh `javac`, ví dụ JDK 17, 21 hoặc 25. Kiểm tra bằng `javac -version`. Nó quyết định những `--release` nào compiler hỗ trợ, phiên bản của compiler và môi trường build tools/annotation processors.

**Release đích (target platform release)** là mức Java mà chúng ta muốn class file và API nền tảng của chương trình tương thích. Lựa chọn khuyến nghị khi dùng `javac` hiện đại là `--release N` (nếu compiler hỗ trợ N). Nó ràng buộc cả **cú pháp/ngôn ngữ**, **định dạng class file**, và **API Java/JDK được mô tả cho release N**.

**Runtime/JRE/JVM triển khai (deployment runtime)** là môi trường thực sự chạy lệnh `java`. Một runtime Java 11 không có nhiệm vụ hiểu class file Java 17; runtime Java 17 hoặc mới hơn về nguyên tắc có thể đọc class file được tạo cho Java 11, với các điều kiện tương thích khác vẫn phải đáp ứng.

**Dependency và platform** gồm thư viện/JAR, Java modules, API hệ điều hành, thư viện native, processor, công cụ build, cấu hình khởi động và các hành vi được ứng dụng dựa vào. Chỉ kiểm tra class chính mà bỏ dependency có thể dẫn đến thất bại khi nạp lớp hoặc gọi API.

~~~text
Build JDK (javac version)
       │
       ├── --release N
       │       ├── Java source rules
       │       ├── class-file major version
       │       └── documented platform API of release N
       │
       ▼
  App classes + dependencies + resources + metadata
       │
       ├── Runtime Java N  ───► compile-time/linkage/runtime tests
       ├── Runtime Java N+ ───► compile-time/linkage/runtime tests
       └── OS/CPU variants ───► integration/platform tests
~~~

Ví dụ: `JDK 21 javac` biên dịch `--release 17` không có nghĩa chương trình sẽ chạy **trên JDK 21** khi phát hành; nó nhằm tạo ứng dụng có cơ hội chạy trên **Java 17** hoặc mới hơn. Phải thực sự dùng Java 17 runtime để chứng minh điều đó.

## 2. Ba cờ --release, --source và --target khác nhau thế nào?

| Cấu hình | Quy định chính | Rủi ro nếu dùng nhầm |
| --- | --- | --- |
| `javac --release 17` | Ngôn ngữ Java 17, class file mục tiêu Java 17, API Java/JDK được phép trong Java 17 | Vẫn không khóa phiên bản của thư viện bên ngoài, runtime flags hay native dependencies |
| `javac --source 17` | Quy tắc ngôn ngữ Java 17 | Một mình cờ này không chứng minh class file và platform API phù hợp Java 17 |
| `javac --target 17` | Class-file version thích hợp với Java 17 | Một mình cờ này không giới hạn API được sử dụng ở bản JDK mới hơn |
| `javac -source 17 -target 17` | Giới hạn source language và class-file target | Nếu không cấu hình platform API đúng, vẫn có nguy cơ dùng API xuất hiện sau Java 17 |
| Không có cờ | Mặc định theo compiler hiện tại | Đổi build JDK có thể vô tình nâng yêu cầu runtime tối thiểu |

**Quy tắc thực hành:** khi dùng `javac` mới để xây ứng dụng chạy trên release Java cũ hơn, ưu tiên `--release N`. Nó tránh lỗi thường gặp: file `.class` trông tương thích nhưng lại chứa lời gọi tới một method **chỉ có trên Java mới hơn**.

Ví dụ, trên JDK 21:

~~~bash
javac --release 17 -d out src/example/App.java
~~~

Nghĩa là compiler phải từ chối cú pháp hoặc platform API ngoài Java 17, và sinh class file target Java 17 khi biên dịch thành công. Tuy nhiên `--release` **không ép** tất cả các JAR ngoài Java platform trên `-cp` phải được biên dịch bằng target 17, cũng không hạ API của thư viện thứ ba.

**Không kết hợp** `--release` với `--source` hoặc `--target` trong cùng lời gọi; đây là hai cách cấu hình khác nhau. Release được hỗ trợ phụ thuộc đúng `javac` đang dùng: dùng `javac --help` để liệt kê, không giả định một JDK bất kỳ luôn có khả năng cross-compile mọi release trong lịch sử.

## 3. Class-file major version: biết code yêu cầu JVM tối thiểu nào

Class file có major/minor version. Đối với các bản Java hiện đại, những con số thường cần biết:

| Java release | Major version của class file | Ví dụ đối tượng |
| --- | ---: | --- |
| Java 8 | 52 | `javac --release 8` trên JDK hỗ trợ |
| Java 11 | 55 | `javac --release 11` |
| Java 17 | 61 | `javac --release 17` |
| Java 21 | 65 | `javac --release 21` |
| Java 25 | 69 | `javac --release 25` |
| Java 26 | 70 | `javac --release 26` |
| Java 27 | 71 | `javac --release 27` |

Các bản cụ thể kể từ Java 9 tăng major version theo mỗi Java release; bảng trên chỉ chọn mốc phổ biến. `javac` cũ hơn không thể target release tương lai chưa biết, ví dụ `javac` JDK 17 sẽ không nhận `--release 21`. Class-file **major version là điều kiện cần**, nhưng không phải điều kiện đủ cho ứng dụng chạy thành công.

### Cách kiểm chứng thực tế

**Tệp `HelloMatrix.java`:**

~~~java
public class HelloMatrix {
    public static void main(String[] args) {
        System.out.println("Compatibility OK");
    }
}
~~~

Trên máy có `javac` hỗ trợ release 11 và 17:

~~~bash
mkdir -p out11 out17
javac --release 11 -d out11 HelloMatrix.java
javac --release 17 -d out17 HelloMatrix.java
javap -verbose -classpath out11 HelloMatrix
javap -verbose -classpath out17 HelloMatrix
~~~

Trong output của `javap -verbose`, tìm hai dòng `minor version` và `major version`. Với mã **không dùng preview** này, kết quả mong đợi:

~~~text
out11: major version: 55
out17: major version: 61
~~~

Hai dòng trên là **giá trị cần đối chiếu**, không phải toàn bộ stdout của `javap`. Cùng mã nguồn và cùng build JDK nhưng chọn `--release` khác nhau có thể cho class file yêu cầu runtime tối thiểu khác nhau.

Nếu chạy bằng một Java runtime 17:

~~~bash
java -cp out11 HelloMatrix
java -cp out17 HelloMatrix
~~~

Mỗi lệnh in:

~~~text
Compatibility OK
~~~

Nếu thực sự có runtime Java 11, chạy:

~~~bash
/path/to/jdk11/bin/java -cp out11 HelloMatrix
~~~

Lệnh cũng phải in `Compatibility OK` khi cấu hình bình thường; nhưng chạy `out17` bằng Java 11 sẽ bị từ chối vì major 61 mới hơn major tối đa 55 mà Java 11 hỗ trợ. Kiểu lỗi thường gặp là `UnsupportedClassVersionError`. **Chỉ chạy lệnh với đường dẫn runtime đã được cài thật**; `/path/to/jdk11/bin/java` là chỗ thay thế minh họa, không phải chương trình có sẵn trên mọi máy.

## 4. Ví dụ kiểm tra rào cản Java API: target đúng chưa đủ nếu chỉ dùng -target

Một sai lầm cổ điển: giới hạn class-file target nhưng vô tình gọi API từ JDK dùng để build, không tồn tại trên Java đích.

**Tệp `ApiGuard.java`:**

~~~java
public class ApiGuard {
    public static void main(String[] args) {
        System.out.println("   ".isBlank());
    }
}
~~~

`String.isBlank()` xuất hiện từ Java 11, không có trên Java 8. Khi dùng JDK mới có `--release 8`:

~~~bash
javac --release 8 ApiGuard.java
~~~

Compiler **phải từ chối** lời gọi `isBlank()` trên `String` do API chưa tồn tại ở Java 8. Thông báo thường là `cannot find symbol`; không dựa vào một văn bản diagnostic cố định giữa các phiên bản compiler.

Vẫn trên JDK mới đó:

~~~bash
javac --release 11 ApiGuard.java
java ApiGuard
~~~

Với runtime Java 11+ thích hợp, stdout:

~~~text
true
~~~

Điểm mấu chốt: cấu hình tương tự `-source 8 -target 8` trên JDK có `String.isBlank()` **có thể** biên dịch mã nếu compiler vẫn nhìn thấy platform API hiện tại (kèm warning về bootstrap/system classes). Class file có major 52 nhưng khi chạy Java 8 và đến lời gọi `isBlank()` có thể ném `NoSuchMethodError`. Vì vậy **không kiểm tra tương thích chỉ bằng major version**.

Đừng dùng `-source`/`-target` rời rạc để né lỗi `--release`. Nếu buộc phải dùng cặp option cũ vì hoàn cảnh đặc biệt, phải cấu hình platform classes/API tương ứng phiên bản đích và kiểm tra với runtime thật.

## 5. Ví dụ kiểm tra rào cản cú pháp nguồn

Cú pháp Java phát triển theo release. Một API có sẵn không có nghĩa mọi cú pháp mới cũng được compiler chấp nhận khi target Java cũ.

**Tệp `RecordGuard.java`:**

~~~java
public record RecordGuard(int x, int y) {
    public static void main(String[] args) {
        System.out.println(new RecordGuard(2, 3).x());
    }
}
~~~

`record` trở thành tính năng chuẩn từ Java 16. Với JDK 17 hoặc mới hơn hỗ trợ release tương ứng:

~~~bash
javac --release 17 RecordGuard.java
java RecordGuard
~~~

Stdout:

~~~text
2
~~~

Nhưng:

~~~bash
javac --release 11 RecordGuard.java
~~~

sẽ thất bại vì ngôn ngữ Java 11 không có record declaration. Đừng chờ đến JVM Java 11 mới phát hiện sự không phù hợp: compiler đã từ chối theo luật source language của `--release 11`.

Các mốc cần nhớ thêm: `var` cho biến local (Java 10), switch expression (chuẩn Java 14), pattern matching cho `instanceof` và records (chuẩn Java 16), sealed classes (chuẩn Java 17). Nhiều tính năng từng ở trạng thái *preview* trước khi chuẩn hóa; **không dùng phiên bản preview cũ để suy ra source API hoặc bytecode của bản chuẩn**.

## 6. Ma trận lý thuyết: build JDK × release × runtime

Một ma trận ban đầu giúp phát hiện cấu hình **không thể** hoặc **có khả năng** chạy. Với chương trình Java thông thường không dùng preview, dependency phù hợp và JDK compiler hỗ trợ `--release` như bảng:

| Build JDK | `--release` | JVM 11 | JVM 17 | JVM 21 | JVM 25 | Diễn giải |
| --- | --- | --- | --- | --- | --- | --- |
| 17 | 11 | Có thể | Có thể | Có thể | Có thể | Class major 55; cần test API/runtime |
| 17 | 17 | **Không** | Có thể | Có thể | Có thể | Java 11 không đọc major 61 |
| 17 | 21 | Không biên dịch | — | — | — | `javac` JDK 17 không target Java 21 |
| 21 | 11 | Có thể | Có thể | Có thể | Có thể | Compiler mới cross-compile về Java 11 |
| 21 | 17 | **Không** | Có thể | Có thể | Có thể | Runtime từ 17 trở lên về nguyên tắc hỗ trợ major 61 |
| 21 | 21 | **Không** | **Không** | Có thể | Có thể | Class major 65 |
| 25 | 17 | **Không** | Có thể | Có thể | Có thể | Giới hạn platform API theo `--release 17` |
| 25 | 25 | **Không** | **Không** | **Không** | Có thể | Class major 69 |

**“Có thể” không phải “đã PASS”.** Nó chỉ nói điều kiện class-file version chưa loại trừ chạy chương trình. Runtime thực có thể thất bại vì dependency, service providers, reflection/module access, native library, encoding/timezone, security policy hoặc hành vi ứng dụng.

Ma trận này xem runtime 11/17/21/25 như các **môi trường có thể triển khai**, không buộc ứng dụng nào cũng phải hỗ trợ đủ bốn phiên bản. Khi chính sách sản phẩm tuyên bố “Java tối thiểu 17”, cột Java 11 nằm ngoài phạm vi support; không cần xây nhánh riêng để ép code Java 17 về 11 chỉ cho đẹp bảng.

### Cách chọn ma trận hữu ích thay vì nhân tổ hợp vô hạn

- **Hàng:** các JDK được phép dùng để build trong CI/dev/release, ví dụ 17 và 21.
- **Cột:** các runtime mà sản phẩm tuyên bố hỗ trợ, ví dụ 17 và 21.
- **Điều kiện cố định:** `--release 17` cho artifact production, cùng lockfile/dependency versions, cùng bộ test quan trọng.
- **Bổ sung trục nền tảng** khi có native dependencies hoặc hệ điều hành/CPU có tác động (Linux, Windows, ARM/x86_64...).
- **Không test JDK tương lai chỉ vì có sẵn:** chọn theo policy hỗ trợ và rủi ro thực tế; runtime rất mới vẫn cần xác nhận hành vi.

## 7. Runtime tối thiểu không đồng nghĩa “chạy được trên mọi Java mới”

Mặc dù Java cố duy trì tính tương thích ngược, một artifact bytecode cũ không có bảo đảm tuyệt đối rằng mọi chức năng còn hoạt động trên mọi JVM mới. Những nguyên nhân cần chú ý:

1. **Thư viện Java đã bị loại bỏ hoặc không còn kèm JDK**. Ví dụ Java EE/JAXB modules từng được đóng kèm một số JDK cũ nhưng được loại khỏi JDK 11; nếu app cũ dựa vào chúng, class file cũ vẫn không có dependency lúc chạy.
2. **Strong encapsulation/JDK internals**. Mã truy cập `sun.*` hoặc các package nội bộ có thể thất bại với JDK mới hoặc yêu cầu điều chỉnh `--add-exports`/`--add-opens` (không phải giải pháp bền vững).
3. **Runtime flags hoặc GC**. Một option launcher/VM có thể đổi hoặc bị loại bỏ; app có thể không khởi động dù class files tương thích.
4. **Thư viện bên ngoài**. JAR mới hơn có thể dùng class-file major cao hơn; hoặc API của dependency được thay đổi không tương thích.
5. **Native code/JNI, TLS/crypto, locale, timezone, file permissions**. Phần ngoài bytecode phụ thuộc hệ điều hành, chính sách bảo mật và JDK runtime image.
6. **Reflection, proxies, service loading và module boundaries**. Một số lỗi chỉ xảy ra khi chạy một code path cụ thể, không phải khi kiểm tra `main` khởi động.

Vì vậy, ma trận hỗ trợ nên gồm test **compile**, **run trên runtime đích**, **integration với dependencies**, và **regression** cho những chức năng nhạy cảm. Định dạng class file chỉ là một rào cản đầu tiên.

## 8. Dependency quyết định JVM tối thiểu của toàn ứng dụng

Giả sử `app.jar` được biên dịch `--release 11` (major 55), nhưng `lib-x.jar` chứa lớp major 61 (Java 17). Nếu Java 11 runtime phải nạp class major 61 ấy, kết quả có thể là `UnsupportedClassVersionError` dù `app.jar` tự thân hợp lệ.

**Khả năng tương thích là thuộc tính của cả tập runtime artifacts**, không chỉ một class do project tạo. Với các dependency bên ngoài còn cần đối chiếu:
- Phiên bản Java tối thiểu được nhà phát hành thư viện công bố.
- Class-file version của các lớp thực sự được nạp, cả thư viện gián tiếp/transitive dependencies.
- Các API system module hoặc JDK internals thư viện gọi.
- Điều kiện khởi tạo và tương thích nhị phân giữa các phiên bản library.
- Các dependency được nạp động: JDBC driver, service provider, servlet container, plugin, agent, bytecode transformer.

Ví dụ kiểm tra class file trong một JAR:

~~~bash
jar tf libs/example.jar
javap -verbose -classpath libs/example.jar com.example.SomeClass
~~~

**Lệnh là mẫu minh họa:** cần thay `libs/example.jar` và `com.example.SomeClass` bằng JAR/tên class có thật. `jar tf` hiển thị entries; `javap` hiển thị major/minor version **cho một class**, không tự quét toàn bộ JAR. Muốn xác nhận mọi class và cả multi-release entries, phải sử dụng công cụ phân tích JAR/CI thích hợp, không lấy một class làm kết luận toàn bộ thư viện.

### Multi-release JAR

Một JAR có thể chứa versioned classes dưới `META-INF/versions/N/` theo cơ chế **multi-release JAR**. Runtime thích hợp sẽ chọn entry phù hợp với phiên bản của nó. Đây là cách cung cấp các implementation khác nhau theo release, nhưng **không đồng nghĩa** một class tùy ý major 61 nằm trong JAR đều chạy được trên Java 11.

Cần có base classes hợp lệ cho runtime tối thiểu, manifest/định dạng JAR đúng và kiểm chứng đường chọn versioned entry. Nếu phân tích class file bằng `javap`, lưu ý option lựa chọn multi-release version khi thích hợp; chỉ xem base entry có thể bỏ sót bytecode mà runtime mới hơn chọn.

## 9. Preview features là trục kiểm tra khác release thông thường

Một số tính năng Java được cung cấp ở trạng thái preview trong từng JDK, có thể đổi hoặc bị rút trước khi chuẩn hóa. Compile preview có quy tắc riêng về `--enable-preview`, release của compiler và cách chạy.

Ví dụ tổng quát cho **mã thực sự dùng preview của đúng JDK đang biên dịch**:

~~~bash
javac --enable-preview --release 21 PreviewDemo.java
java --enable-preview PreviewDemo
~~~

Lệnh trên là **mẫu cú pháp** cho hoàn cảnh dùng JDK 21; `PreviewDemo.java` không được cung cấp ở đây vì nội dung phải chọn theo tính năng preview cụ thể của release đó. Trên `javac` mới khác, không nên mặc định nó hỗ trợ compile preview của release lịch sử.

Thông thường, preview class file dùng minor version đặc biệt `65535` cùng major version của release tương ứng; JVM chỉ cho phép preview ở điều kiện phù hợp, bao gồm `--enable-preview` và release tương ứng. Ví dụ, bytecode preview của Java 21 không được xem là một artifact portable bình thường cho runtime Java 25.

**Khuyến nghị:** nếu mục tiêu là một thư viện phát hành rộng rãi, tránh preview trong bản artifact hỗ trợ nhiều runtime. Nếu dùng preview, định nghĩa rõ **cặp JDK build + runtime exact release + flags**, tách khỏi bảng compatibility phổ thông. Việc test pass trên Java 21 có bật preview không chứng minh ứng dụng chạy Java 21 không bật preview.

## 10. Ví dụ mini-project thực hành: build một lần, chạy nhiều runtime

Tạo thư mục riêng:

~~~text
matrix-demo/
├── src/
│   └── demo/
│       ├── Calculator.java
│       └── Main.java
└── out17/
~~~

**`src/demo/Calculator.java`**

~~~java
package demo;

public final class Calculator {
    private Calculator() {
    }

    public static long add(long a, long b) {
        return Math.addExact(a, b);
    }
}
~~~

**`src/demo/Main.java`**

~~~java
package demo;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println("result=" + Calculator.add(20, 22));
    }
}
~~~

Từ thư mục `matrix-demo`, dùng JDK 17+ hỗ trợ release 17:

~~~bash
mkdir -p out17
javac --release 17 -encoding UTF-8 -d out17 \
  src/demo/Calculator.java src/demo/Main.java
java -cp out17 demo.Main
~~~

Stdout:

~~~text
result=42
~~~

`Math.addExact(long, long)` có từ Java 8 nên không gây vấn đề API khi target Java 17. Ví dụ cố tình dùng cú pháp đơn giản và một API đã tồn tại trước target để người học tập trung vào **ma trận runtime**, không vào sự thay đổi cú pháp.

Nếu máy có nhiều JDK, thay lệnh `java` trong bước cuối bằng đường dẫn của **runtime cụ thể**:

~~~bash
/opt/jdk17/bin/java -cp out17 demo.Main
/opt/jdk21/bin/java -cp out17 demo.Main
/opt/jdk25/bin/java -cp out17 demo.Main
~~~

Các đường dẫn `/opt/jdk17`, `/opt/jdk21`, `/opt/jdk25` là **ví dụ**, phải thay bằng nơi đã cài JDK trên máy/runner. Mỗi môi trường hợp lệ đều nên in `result=42`; lúc chạy nhớ dùng binary `java` của đúng JDK, không chỉ xem `JAVA_HOME` trong terminal.

**Tách build khỏi run:** nếu bạn dùng JDK 25 `javac` để biên dịch `--release 17`, bước run trên JDK 17 vẫn phải được test bằng `/opt/jdk17/bin/java`. Việc chạy bằng `java` trong PATH có thể vô tình dùng JDK 25 và tạo kết quả xanh giả cho hỗ trợ Java 17.

## 11. Ma trận xác minh bằng lệnh: mỗi artifact, nhiều runtime

Để thực thi thủ công một ma trận nhỏ, chuẩn bị môi trường có Java 17 và Java 21 ở hai đường dẫn khác nhau. Thử mã mẫu mục 10. Sau khi biên dịch xong:

~~~bash
/opt/jdk17/bin/java -version
/opt/jdk17/bin/java -cp out17 demo.Main

/opt/jdk21/bin/java -version
/opt/jdk21/bin/java -cp out17 demo.Main
~~~

**Kết luận “PASS”** chỉ khi lệnh dùng runtime đúng, exit code bằng 0 và stdout đúng kỳ vọng (đối với case này là `result=42`). `java -version` thường ghi thông tin lên stderr; không so sánh đầu ra `-version` với stdout chương trình.

Ma trận mẫu cho artifact `--release 17`:

| Phép thử | Kỳ vọng |
| --- | --- |
| Build với JDK 17, `--release 17` | Compile thành công nếu môi trường đầy đủ |
| Build với JDK 21, `--release 17` | Compile thành công, class-file major 61 |
| Run trên Java 17 | `result=42`, exit 0 |
| Run trên Java 21 | `result=42`, exit 0 |
| Run trên Java 11 | **Không hỗ trợ**, class major 61 |
| Run với dependency không tương thích | Test phải **thất bại rõ ràng**, không được đánh dấu PASS |

Nếu một JDK build mới hơn dẫn đến warnings khác hoặc cấu trúc class file khác nhưng đều hợp lệ theo `--release 17`, không tự cho rằng artifact hỏng. Tuy nhiên, annotation processor/generator có thể hoạt động khác khi đổi JDK, nên artifact pipeline cần test như đầu ra mới, không chỉ xác nhận lệnh `javac` trả 0.

## 12. Tự động hóa test bằng Bash trên CI runner

Đây là script ví dụ chạy trên Linux/macOS, giả sử đã biên dịch thành công `out17/` và có hai biến môi trường **`JAVA17_HOME`**, **`JAVA21_HOME`** trỏ tới thư mục cài đúng Java runtimes. Script test exit code và stdout của ứng dụng, không tự ý cài JDK:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

for home in "$JAVA17_HOME" "$JAVA21_HOME"; do
    "$home/bin/java" -version

    actual="$("$home/bin/java" -cp out17 demo.Main)"
    if [[ "$actual" != "result=42" ]]; then
        printf 'FAIL: unexpected output: %s\n' "$actual" >&2
        exit 1
    fi

    printf 'PASS: %s\n' "$home"
done
~~~

Chạy script này từ thư mục project có `out17`. Với `set -e`, lệnh Java không trả exit code 0 sẽ dừng pipeline, kể cả khi biến `actual` không được gán đầy đủ. Dữ liệu đầu ra so sánh đúng chuỗi nhỏ này; với chương trình phức tạp nên dùng JUnit/integration tests thay vì dựa vào stdout đơn lẻ.

**Giới hạn của script:** nếu `JAVA17_HOME` hoặc `JAVA21_HOME` không được đặt, script báo lỗi; cần cấu hình CI/runner. Nếu các biến trỏ nhầm cùng một JDK, hai test không thực sự phủ hai runtime khác nhau. Vì vậy ở đầu mỗi job hãy **ghi và xác nhận phiên bản thực tế**, không chỉ in nhãn “Java 17”.

Một cách CI phổ biến là **matrix strategy**: mỗi job chạy một runtime, ví dụ Java 17 và 21, để giảm nguy cơ dùng nhầm `java`. Điều này cho phép báo riêng PASS/FAIL từng Java version và chạy nhiều job song song.

## 13. Phân biệt build matrix và runtime matrix

Có hai dạng kiểm thử cần được tách:

**Build matrix** trả lời “source/build pipeline có build được bằng JDK nào?” Ví dụ chạy cùng source với JDK 17 và JDK 21, luôn đặt `--release 17`. Nó phát hiện khác biệt compiler, processor, generator và build tool khi JDK thay đổi.

**Runtime matrix** trả lời “cùng một artifact đã build có chạy được ở các Java runtime tuyên bố hỗ trợ không?” Ví dụ build một artifact bằng JDK 21 `--release 17`, rồi chạy chính artifact đó dưới Java 17 và 21.

Nếu mỗi runtime job tự build lại artifact, bạn đang kiểm tra **cặp build JDK–runtime** chứ không thuần túy kiểm tra **cùng một artifact trên nhiều runtime**. Cả hai đều hữu ích; nên thiết kế có chủ đích:

~~~text
                  build JDK 17 ──┐
source + deps ────┤             ├──► build validation
                  build JDK 21 ──┘

source + deps ──► canonical build JDK 21 --release 17
                            │
                            ▼
                   SAME artifact (hash)
                    │               │
                    ▼               ▼
                Java 17          Java 21
                    │               │
                    └──► runtime/test matrix
~~~

Đối với phát hành, **canonical release artifact** là tệp được deploy thật. Dùng cùng SHA-256/artefact identifier trong các runtime jobs thay vì mỗi job tạo một build có thể hơi khác. Đồng thời, đặt một job riêng để xác minh việc đổi build JDK không phá toolchain.

## 14. Cấu hình Maven và Gradle theo target release

Với Maven, có thể khai trong `pom.xml`:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

Thuộc tính này được Maven Compiler Plugin hỗ trợ ở các phiên bản phù hợp. Compiler được lựa chọn vẫn phải hỗ trợ `--release 17`; cấu hình Maven **không cài đặt JDK 17**. Nếu CI cần JDK cụ thể, dùng Maven Toolchains Plugin hoặc cấu hình runner/IDE phù hợp.

Gradle (Groovy DSL) có thể khai:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

Ý nghĩa: **chọn JDK 21 làm compiler toolchain** (khi Gradle/toolchain resolution có JDK đó), nhưng chỉ **phát class file và tham chiếu platform APIs theo Java 17**. Đây là hai trục độc lập. Cấu hình Gradle runtime test/tasks phải kiểm tra riêng: target release của compiler không tự đổi `java` launcher dùng trong mọi task thử nghiệm hoặc khi triển khai.

**Cảnh báo thường gặp:** `sourceCompatibility = '17'` và `targetCompatibility = '17'` không cung cấp cùng bảo đảm API giống `options.release = 17`. Hãy xem lệnh `javac` thực sự được Gradle/Maven gọi và kiểm tra class-file version trong artifact.

### Annotation processors và build plugins cũng có mức JDK riêng

Ví dụ dự án chạy target Java 17 nhưng annotation processor hoặc build plugin yêu cầu JDK 21. Khi build dưới JDK 17, toolchain có thể thất bại dù source code chính hoàn toàn hợp lệ với Java 17. Processor/plugin là **chương trình chạy trong môi trường build**, không nhất thiết bị giới hạn bởi `--release` của output ứng dụng.

Trên các phiên bản JDK mới, chính sách kích hoạt annotation processing cũng thay đổi (từ JDK 23, processing cần được cấu hình rõ hơn). Khi test build matrix, cấu hình processor được enable và processor path rõ ràng nếu build phụ thuộc code generation. Nếu bỏ qua bước này, build có thể “thành công” nhưng thiếu lớp sinh tự động.

## 15. Dependency version, công cụ đóng gói và runtime image

**Maven/Gradle dependency graph** phải được cố định hợp lý bằng dependency locking/BOM/reproducible build tùy dự án. Nếu Java 17 job lấy một dependency version, Java 21 job lấy version khác, không thể quy một lỗi đơn giản là do JDK.

**Fat JAR hoặc shaded JAR:** cần rà soát mọi class được gộp vào artifact, không chỉ những class nằm trong thư mục chính của project. Thư viện có thể được relocation nhưng bytecode version vẫn không tự hạ.

**jlink runtime image:** custom runtime image có thể bỏ bớt modules. Một ứng dụng compile `--release 17` vẫn có thể lỗi khi runtime image thiếu một module cần thiết. Cần test trên **chính image được phát hành**, không chỉ JDK đầy đủ của nhà phát triển.

**Container:** cặp “build image Java 21” và “runtime image Java 17” có thể hợp lệ nếu target đúng, dependencies tương thích, và entrypoint/classpath đúng; phải kiểm tra image tags, digest và runtime version bên trong container. Nếu runtime image là Java 11, artifact Java 17 sẽ thất bại dù Docker build hoàn tất.

**Native dependencies:** Java source level không quyết định binary compatibility của native library `.dll`/`.so`/`.dylib`. Lập thêm trục kiểm thử OS/architecture và phiên bản JNI/FFM (nếu dùng) khi triển khai nhiều nền tảng.

## 16. Những lỗi tiêu biểu trong ma trận và cách đọc

### UnsupportedClassVersionError

Ví dụ Java 11 runtime nạp `HelloMatrix.class` được biên dịch với `--release 17`. Lý do là class file major 61 vượt hỗ trợ của Java 11 (55). Sửa bằng cách **dùng runtime mới phù hợp** hoặc **biên dịch lại source/dependency với target thấp hơn thật sự được hỗ trợ**, rồi test lại. Không được chỉnh byte major bằng hex editor: bytecode/API vẫn có thể không tương thích.

### NoSuchMethodError hoặc NoSuchFieldError

Class file có thể đúng major nhưng runtime nạp một **phiên bản thư viện** không có method/field mà code đã được compile để gọi, hoặc JDK API runtime cũ hơn. Kiểm tra classpath/module path, version conflict, shadowing, và API có mặt ở target release không. Với platform API, `--release` giúp chặn lỗi do vô tình gọi API mới hơn.

### NoClassDefFoundError và ClassNotFoundException

Dependency có thể thiếu ở runtime, runtime image bị cắt module, hoặc lớp không được nạp. Đây không phải bằng chứng class-file major sai. Kiểm tra artifact thực tế, cách resolve dependencies, plugin/service loader và đường dẫn.

### IllegalAccessError, InaccessibleObjectException

Có thể do thay đổi module boundaries/strong encapsulation giữa các JDK hoặc code reflection truy cập internals. Cần xác nhận `module-info.java`, `exports`/`opens` hoặc thay thế bằng public API; việc bật cờ đặc biệt ở compiler không đảm bảo runtime đã nhận cùng option.

### NoSuchAlgorithmException, TLS/cipher lỗi, thay đổi encoding

Đây thường là vấn đề runtime environment/security/provider hoặc dữ liệu. Java cũ/mới có default và policy khác nhau. Unit test “Hello World” không bao phủ những tương tác này; thêm integration tests theo workload thực.

### Khác biệt test do timezone, locale, default charset

Một ứng dụng không chỉ phụ thuộc bytecode. Ví dụ Java 18 chuyển default charset của JDK sang UTF-8 theo JEP 400; mã cũ mặc định theo encoding hệ điều hành có thể cho kết quả khác. Với test có dữ liệu văn bản, hãy chỉ định charset (`StandardCharsets.UTF_8`) và locale/timezone khi yêu cầu ổn định.

## 17. Dùng javap và runtime version để chẩn đoán nhất quán

Khi báo lỗi ma trận, giữ tối thiểu bộ chứng cứ:

~~~bash
javac -version
java -version
javac --help
javap -verbose -classpath out17 demo.Main
~~~

`javap` hữu ích cho major/minor version, chữ ký, method descriptors, references và metadata. Tuy nhiên, nó chỉ kiểm tra **class được chỉ rõ**. Đối với file JAR phức tạp, kiểm tra các dependency/transitive classes thực sự cần nạp.

Khi chạy trên CI, log chính xác **đường dẫn** `java`/`javac` và phiên bản, không chỉ đọc `JAVA_HOME`. Runner có thể có nhiều bản JDK; `PATH`, toolchains của build tool, plugin hoặc IDE đôi khi chọn khác nhau. Cùng source và cùng flags cũng có thể cho output khác giữa compiler versions, nhưng điều quyết định runtime compatibility là khả năng nạp, liên kết và chạy đúng, chứ không phải toàn bộ bytecode phải giống từng byte.

Bắt lỗi kiểu phiên bản ở **cả bước biên dịch** và **bước thực thi**. Một môi trường chỉ có JDK 21 có thể dùng `javac --release 17` và chạy bằng Java 21, nhưng không tự chứng minh Java 17 runtime có thể triển khai mọi tính năng thực tế.

## 18. Checklist phát hành và quyết định PASS/FAIL

Trước khi tuyên bố “chúng tôi hỗ trợ Java 17+”:

1. **Chốt target Java tối thiểu**, không chọn theo bản JDK ngẫu nhiên của nhà phát triển.
2. **Kiểm tra tất cả build JDK được phép**, `javac -version` và những release mà compiler thực sự hỗ trợ.
3. **Đặt `--release N`**, hoặc cơ chế tương đương của build tool, trong từng module/compile task; không dùng `-target N` đơn lẻ.
4. **Kiểm tra artifact**: major/minor version, dependency JAR, class sinh tự động, fat JAR, multi-release entries và module graph.
5. **Test runtime đích thấp nhất** (ví dụ Java 17), vì đây là nơi dễ lộ lỗi thiếu API/classfile hơn.
6. **Test thêm runtime mới được hỗ trợ** (ví dụ Java 21/25) để bắt lỗi module reflection, JDK removal, default security/provider/encoding và behavior changes.
7. **Chạy integration smoke test, unit test, I/O, DB/TLS, serialization, reflection và native code** theo phạm vi sản phẩm, không chỉ lệnh in chuỗi.
8. **Tách build matrix và runtime matrix**; dùng **cùng release artifact** trong runtime jobs nếu muốn chứng minh portability của một bản phát hành.
9. **Ghi lại chính sách preview**, khuyến nghị không dùng cho library/runtime matrix đại trà; nếu bắt buộc, cố định đúng version và `--enable-preview`.
10. **Báo kết quả có điều kiện**: PASS ở JDK nào, OS nào, artifact digest nào, với bộ test nào. Không biến “class major được JVM hỗ trợ” thành “đã chứng minh mọi chức năng”.

### Mẫu bảng kết quả thực nghiệm

| Artifact | Build JDK | Release | Runtime | Loại kiểm tra | Kết quả |
| --- | --- | --- | --- | --- | --- |
| `app.jar` (SHA cố định) | 21 | 17 | 17 | Smoke + unit + integration | PASS/FAIL thực đo |
| Cùng `app.jar` | 21 | 17 | 21 | Smoke + unit + integration | PASS/FAIL thực đo |
| Cùng `app.jar` | 21 | 17 | 25 | Smoke + unit + integration | PASS/FAIL thực đo |
| Build thử cùng source | 17 | 17 | 17 | Build tool + processor | PASS/FAIL thực đo |

Các ô `PASS/FAIL thực đo` là **vị trí ghi kết quả sau khi chạy CI**, không phải kết luận trước. Nếu runtime 25 chưa nằm trong chính sách hỗ trợ, hàng tương ứng có thể được đánh dấu “experimental” thay vì phát hành lời hứa không kiểm chứng.

## 19. Câu hỏi tự kiểm tra

**Câu 1.** Build bằng JDK 21 với `--release 17`: có nhất thiết phải chạy bằng Java 21 runtime không?  
**Trả lời:** Không. Artifact được nhắm tới Java 17 platform; hãy test với Java 17 và các runtime được hỗ trợ.

**Câu 2.** `javap` báo major 55 nhưng ứng dụng gọi `String.isBlank()`. Có đảm bảo chạy Java 8 không?  
**Trả lời:** Không. Java 8 không có `String.isBlank()`; `-source 8 -target 8` với platform API mới có thể sinh file major 52 mà vẫn chứa tham chiếu API mới. Với major 55 (Java 11) lại càng không thể chạy Java 8.

**Câu 3.** Vì sao `--release 8` từ JDK mới đáng tin cậy hơn `-source 8 -target 8`?  
**Trả lời:** Nó ràng buộc cả ngôn ngữ, class-file target và platform API được phép ở Java 8, không chỉ cú pháp/bytecode.

**Câu 4.** Một `app.jar` có class major 61, nhưng một dependency có major 65. Java 17 runtime có thể load dependency ấy không?  
**Trả lời:** Không. Java 17 chỉ hỗ trợ tới major 61; khi class major 65 phải được nạp sẽ gặp lỗi phiên bản.

**Câu 5.** Lý do nào khiến mã đã compile `--release 17` có thể vẫn lỗi trên Java 21 runtime?  
**Trả lời:** Dependencies, JDK internals, module access, runtime flags, native libraries, security/provider hoặc hành vi ngoài class-file format có thể khác; cần test runtime thực.

**Câu 6.** Tại sao hai job đều có nhãn “Java 17” chưa chứng minh ma trận có hai runtime?  
**Trả lời:** Có thể cả hai trỏ nhầm cùng binary `java`; cần ghi `java -version` và đường dẫn thực tế, đồng thời tách toolchain build khỏi runtime.

**Câu 7.** Preview class file từ Java 21 có nên coi portable bình thường sang mọi runtime mới hơn không?  
**Trả lời:** Không. Preview có cờ kích hoạt và ràng buộc phiên bản đặc biệt; không suy như class file ổn định.

**Câu 8.** Vì sao cần test runtime thấp nhất lẫn runtime mới?  
**Trả lời:** Runtime thấp nhất phát hiện class/API yêu cầu quá cao; runtime mới phát hiện thay đổi dependency, module encapsulation, bảo mật, môi trường và hành vi tích hợp.

## 20. Ghi nhớ và nguồn tra cứu

- **Build JDK**, **`--release`**, **class-file major version**, **dependency runtime requirement** và **runtime thực tế** là các trục khác nhau.
- Dùng **`--release N`** khi cần cross-compile tới Java N được hỗ trợ; chỉ `-source`/`-target` chưa đủ để bảo đảm platform API tương thích.
- Ma trận class-file cho biết khả năng cơ bản, **không thay thế runtime tests** với chính Java N và đúng artifact.
- **Không chỉ kiểm tra app class**: thư viện, generated classes, shaded JAR, Java modules và runtime image có thể nâng mức Java tối thiểu.
- **Preview, native code, reflection và JDK internals** yêu cầu chính sách hỗ trợ riêng và test tương ứng.
- Giữ build reproducible, xác nhận `java -version` ở mỗi CI job, lưu artifact digest và kết quả test trước khi tuyên bố PASS.

Tài liệu chính thức: [javac command (Oracle JDK 25)](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html), [Class file format / JVM specification](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-4.html), [JEP 247: Compile for Older Platform Versions](https://openjdk.org/jeps/247), [JEP 238: Multi-Release JAR Files](https://openjdk.org/jeps/238), [JEP 400: UTF-8 by Default](https://openjdk.org/jeps/400).