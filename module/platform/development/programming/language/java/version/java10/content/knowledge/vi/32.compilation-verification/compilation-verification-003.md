# `javac --release` và giới hạn các phiên bản đích mà trình biên dịch hỗ trợ

> **Java 10 — Biên dịch và kiểm chứng.** `javac --release N` là cách chuẩn để dùng **một JDK mới hơn biên dịch mã Java cho một nền tảng Java SE/JDK cũ hơn được hỗ trợ**. Khác với chỉ đặt `-source` và `-target`, tùy chọn này phối hợp **quy tắc cú pháp ngôn ngữ**, **định dạng class file (bytecode)** và **tập API của phiên bản đích**, giúp phát hiện sớm việc vô tình gọi API ra đời sau phiên bản cần hỗ trợ. Nhưng `--release` **không hỗ trợ tất cả phiên bản Java từng tồn tại**, **không thể nhắm đến JDK tương lai**, **không bảo đảm tương thích của mọi thư viện thứ ba hoặc môi trường runtime**. Phạm vi bài này gắn với Java 10 qua các ví dụ `--release 9/10/11`, nhưng hướng triển khai thực tế ưu tiên **JDK đang được cập nhật và hỗ trợ**, chẳng hạn các nhánh LTS được tổ chức sử dụng.

## 1. Mục tiêu học tập

Hoàn thành bài này, bạn có thể:

1. Giải thích cơ chế `--release` được đưa vào `javac` từ **JDK 9** qua **JEP 247**, vẫn là lựa chọn được Oracle khuyến nghị trên các JDK hiện đại.
2. Phân biệt **JDK dùng để biên dịch** (compiler/toolchain), **target release**, **class file version**, **nền tảng API** và **JVM thực sự chạy ứng dụng**.
3. Hiểu ba việc `--release N` kết hợp: cú pháp/source rules của Java N, class-file target của Java N và public/exported platform APIs tương ứng N.
4. Giải thích vì sao `-source 10 -target 10` **không tự giới hạn API** đang có trên JDK biên dịch, còn `--release 10` thì có.
5. Kiểm tra **danh sách release mà chính `javac` đang cài hỗ trợ** bằng `javac --help`; không giả định một dãy cố định trên mọi JDK.
6. Phân biệt một JDK mới **đọc được class file cũ** với khả năng **tạo lại class file nhắm tới mọi release cũ** — hai loại tương thích khác nhau.
7. Dùng ví dụ Java 10: `var` và `List.copyOf` được chấp nhận ở `--release 10` nhưng không ở `--release 9`; `String.repeat` chỉ từ Java 11; `record` chuẩn hóa từ Java 16.
8. Giải thích class-file major version: Java 8 là 52, Java 9 là 53, Java 10 là 54, Java 11 là 55, Java 17 là 61, Java 21 là 65, Java 25 là 69 và Java 27 là 71.
9. Hiểu `--release` không tự kiểm tra reflection, JNI, OS-dependent behavior, configuration, third-party dependencies, security policy hay runtime semantics.
10. Biết giới hạn tùy chọn `--add-exports`, module system options và không dùng compiler flags để phá encapsulation của platform API trong phép biên dịch `--release`.
11. Biên dịch, chạy và kiểm tra class version của `CompatHello.java` trên **JDK mới có hỗ trợ target 10**, nhưng **không coi JDK 10 là runtime nên triển khai production hiện nay**.
12. Chạy `ReleaseMatrixLab.java` trên full JDK 17+ và so sánh đúng **18 dòng stdout** đã kiểm thử trên **JDK 24**, với điều kiện phiên bản compiler có hỗ trợ các target 9, 10, 11, 17.
13. Thiết lập Maven Compiler Plugin và Gradle Java toolchains với release target rõ ràng, phân biệt **toolchain JDK** với **`options.release`**.
14. Thiết kế bước CI: compile, đọc class major, chạy tests trên JDK tối thiểu và hiện tại, kiểm tra dependency bytecode/API, triển khai artifact có provenance.
15. Xác định tình huống cần **chuyển sang toolchain cũ được tổ chức hỗ trợ** hoặc nâng minimum supported runtime nếu compiler mới không còn hỗ trợ target lịch sử.

## 2. Năm lớp “phiên bản Java” rất dễ bị nhầm

Giả sử build server có **JDK 25**, product yêu cầu ứng dụng chạy trên **Java 17**:

| Thuật ngữ | Trong ví dụ | Ý nghĩa |
| --- | --- | --- |
| **Build JDK** | JDK 25 | Cung cấp `javac`, JDK tools, compiler implementation |
| **Source language release** | Java 17 | Quy tắc cú pháp/tính năng ngôn ngữ được phép trong source |
| **Target class-file release** | Java 17 | File `.class` có version thích hợp cho Java 17 |
| **Platform API release** | Java 17 | `javac` chỉ cho sử dụng API Java SE/JDK được hỗ trợ ở release 17 |
| **Runtime đang chạy** | Java 17, 21 hoặc 25 (tùy deployment) | JVM thực sự load classes, link dependencies, chạy chương trình |

Với `javac --release 17` trên JDK 25, bạn **không** biến `javac` thành `javac 17`. Bạn vẫn dùng compiler JDK 25, nhưng yêu cầu nó phát hành class file và hạn chế API/source như Java 17.

### 2.1. Sơ đồ quy trình

```text
Source code .java
        |
        | javac của JDK hiện tại
        | --release 17 (nếu compiler có hỗ trợ)
        v
  [kiểm tra ngữ pháp Java 17]
  [kiểm tra API của nền tảng Java 17]
  [phát class files cho target 17]
        |
        v
    application.jar
        |
        +--> runtime Java 17: cần test thật
        +--> runtime Java 21: cần test thật
        +--> runtime Java 25: cần test thật
        +--> runtime cũ hơn 17: không thể mặc định chạy bytecode 17
```

**Lưu ý:** JVM mới có khả năng nạp nhiều class file cũ, nhưng ứng dụng có thể gặp khác biệt về behavior, removed APIs, security, service providers, classpath/module path hoặc thư viện; chạy được bytecode **không đồng nghĩa** chạy đúng nghiệp vụ.

### 2.2. Ba cấp độ tương thích

**Source compatibility:** mã nguồn có cú pháp và APIs phù hợp để compiler hiểu ở version mục tiêu.

**Binary compatibility:** class files được JVM/runtime đích chấp nhận, linking thành công, thư viện và method signatures tương thích.

**Behavioral compatibility:** ứng dụng thực thi đúng, kết quả và các side effects phù hợp trên runtime thật.

`--release` tăng mức bảo đảm ở **source/platform API/class-file**. Nó không thay thế **integration tests**, compatibility tests hoặc canary deploy.

## 3. `--release` được giới thiệu khi nào?

### 3.1. JEP 247 — Compile for Older Platform Versions

**JEP 247** đưa `--release` vào **JDK 9**. Mục tiêu là cho phép developer dùng một compiler hiện đại phát ra class file cho **một nền tảng cũ hơn** mà không vô tình gọi API chỉ xuất hiện trên JDK build hiện tại.

Trước đó, nhiều dự án chỉ đặt:

```bash
javac -source 8 -target 8 Example.java
```

Ví dụ chỉ để đối chiếu khái niệm; **không khuyến nghị dùng cách này như cấu hình mặc định cho dự án mới**. Nó chọn luật cú pháp và class target nhưng nếu không đồng thời đưa **platform classes đúng Java 8** vào compile environment, compiler có thể vẫn tham chiếu API của JDK mới. Artifact khi đó có thể fail bằng `NoSuchMethodError` hay `NoClassDefFoundError` khi chạy trên runtime cũ dù class major phù hợp.

`--release` giải quyết đúng vấn đề API platform bằng cách chọn phần thông tin nền tảng được gắn với phiên bản đích trong compiler distribution.

### 3.2. Java 10 có vai trò gì?

**Java 10** là ngữ cảnh của module:
- `javac --release 10` là một target mà **những compiler hiện nay nếu vẫn hỗ trợ Java 10** có thể sử dụng để minh họa quy tắc source/API.
- Java 10 cho phép local variable type inference `var` (JEP 286).
- Java 10 bổ sung `List.copyOf`/`Set.copyOf`/`Map.copyOf` (JEP 269 liên quan immutable collection factories từ Java 9, nhưng `copyOf` APIs thuộc Java 10).
- Java 11 bổ sung `String.repeat`.
- Java records trở thành feature chính thức từ Java 16 (JEP 395).

**Không nhầm lịch sử:** `--release` **không được giới thiệu trong Java 10**; nó xuất hiện **trong Java 9** và vẫn có ý nghĩa khi học các tính năng mới của Java 10.

### 3.3. Kiến thức nào còn áp dụng hiện nay?

Trên **Oracle JDK 27** và các JDK được cập nhật:
- `--release` vẫn được `javac` tài liệu hóa.
- Nên chọn một **JDK build hiện hành/được hỗ trợ**.
- Phải xác nhận **supported target values** bằng `javac --help`.
- Mục đích target Java 10 trong bài là **kiểm chứng nguồn gốc các API/tính năng**, không phải lời khuyên đưa một JDK 10 hết vòng đời vào production.
- Nếu sản phẩm yêu cầu Java 17, 21 hoặc 25, hãy đặt `--release` tương ứng và test trên **runtime tối thiểu được phép dùng**, không gắn target 10 chỉ vì đây là module Java 10.

## 4. Cú pháp `javac --release` và ba bảo đảm của nó

### 4.1. Cú pháp cơ bản

```bash
javac --release 17 -d out src/com/example/App.java
```

Lệnh này là **mẫu**: cần file `src/com/example/App.java` có thật và cần `javac` hiện tại hỗ trợ release 17.

| Phần | Ý nghĩa |
| --- | --- |
| `javac` | Dùng compiler đang được chọn bởi environment/toolchain |
| `--release 17` | Luật ngôn ngữ, class target và platform APIs Java 17 |
| `-d out` | Ghi class files vào thư mục `out` |
| `src/com/example/App.java` | Source input |
| `-encoding UTF-8` (nếu cần) | Chỉ định encoding source; không ảnh hưởng target API |
| `-classpath ...` | Third-party/user dependencies; **không** tự ép các JAR này phù hợp target 17 |
| `-proc:none` (phù hợp khi test) | Tắt annotation processing để phép đo/compilation test có tính quyết định |

### 4.2. Bảo đảm thứ nhất — quy tắc ngôn ngữ

`--release 10` cho phép những cấu trúc Java 10 hỗ trợ, chẳng hạn:

```java
var count = 2; // Java 10: local variable type inference.
```

Đây là **một câu lệnh minh họa trong method**, không phải file Java độc lập. `var` là **restricted type name** dùng trong các ngữ cảnh được Java 10 cho phép, **không phải** từ khóa có thể thay mọi kiểu trong field, method parameter hay return type.

Nếu compile source dùng `var` với `--release 9`, `javac` không chấp nhận ngữ nghĩa `var` như local type inference. Cú pháp chính xác và diagnostic message tùy compiler version; **không đóng đinh chuỗi lỗi của một bản JDK** làm hợp đồng.

### 4.3. Bảo đảm thứ hai — class-file major version

Một file `.class` có header:
- 4 bytes magic `0xCAFEBABE`,
- 2 bytes minor version,
- 2 bytes major version.

Các phiên bản class major thường gặp:

| Java release | Class-file major | Dùng cho |
| --- | ---: | --- |
| Java 8 | 52 | Runtime Java 8 trở lên (khi dependency/API phù hợp) |
| Java 9 | 53 | Runtime Java 9 trở lên |
| **Java 10** | **54** | Java 10 trở lên |
| Java 11 | 55 | Java 11 trở lên |
| Java 17 | 61 | Java 17 trở lên |
| Java 21 | 65 | Java 21 trở lên |
| Java 25 | 69 | Java 25 trở lên |
| Java 27 | 71 | Java 27 trở lên |

Với các version hiện đại từ Java 8, cách ghi nhớ thông dụng là **major = release + 44**. Minor version có thể mang ý nghĩa đối với preview features ở các JDK mới; không nên chỉ nhìn major để kết luận đã đáp ứng **mọi** tính năng/điều kiện của runtime.

`javac --release 10` phát file major **54**, không phải major của JDK 24/25/27 đang chạy compiler. Kiểm tra bằng:

```bash
javap -verbose -classpath out CompatHello
```

Tìm dòng `major version: 54`.

**Đừng suy ra** “major 54 nghĩa dependency đã tương thích mọi Java 10 API” hoặc “chương trình chắc chắn chạy đúng”. Đây chỉ là một điều kiện binary tối thiểu.

### 4.4. Bảo đảm thứ ba — tập API của nền tảng đích

Đây là lý do dùng `--release` thay vì chỉ `-source/-target`.

Ví dụ:
- Java 9 có `List.of(...)`.
- Java 10 bổ sung `List.copyOf(...)`.
- Java 11 bổ sung `String.repeat(...)`.

Với cùng JDK 24 compiler:

| Phép thử | Compiler result kỳ vọng | Lý do |
| --- | --- | --- |
| `List.of` với `--release 9` | PASS | API Java 9 |
| `List.copyOf` với `--release 9` | FAIL | API chưa có trước Java 10 |
| `List.copyOf` với `--release 10` | PASS | API Java 10 |
| `"a".repeat(3)` với `--release 10` | FAIL | `String.repeat` từ Java 11 |
| `"a".repeat(3)` với `--release 11` | PASS | API Java 11 |
| `record Point(int x,int y)` với `--release 10` | FAIL | Records chưa là Java 10 syntax |
| `record Point(int x,int y)` với `--release 17` | PASS | Record là tính năng chuẩn trước Java 17 |

Cần phân biệt:
- Một API **được xác định trong nền tảng JDK ở release đó** có thể là Java SE API hoặc **JDK-specific exported API** được tài liệu `javac` cho phép cho target; không nên nói `--release` “chỉ dùng java.* packages”.
- Một class bên thư viện **third-party** không tự bị `--release` rà soát semantic compatibility từng method/behavior theo cùng cách.
- Những internal packages của JDK **không** được mở bằng `--add-exports` như một cách né hạn chế của `--release`.

## 5. Giới hạn các phiên bản đích do một `javac` hỗ trợ

### 5.1. Không có danh sách “Java 1 tới Java 99” cố định

Tài liệu Oracle JDK 27 nói: tập giá trị hợp lệ của `--release` bao gồm **phiên bản hiện tại và một số phiên bản trước đó có giới hạn**, liệt kê trong **`javac` command-line help**.

Tức là:
- Compiler **JDK 17** không hỗ trợ `--release 21`.
- Compiler **JDK 21** không hỗ trợ `--release 25`.
- Compiler **JDK 25** không hỗ trợ `--release 27`.
- Compiler **JDK 27** có thể hỗ trợ nhiều target lịch sử hơn nhưng vẫn phải đọc danh sách của build đang cài.
- Một release quá cũ có thể **không còn được hỗ trợ làm target** trên compiler mới sau khi chính sách retire options được áp dụng.

**Không nên hỏi “Java ngôn ngữ có tồn tại năm nào?” để suy ra `--release N` có thể dùng.** Hãy hỏi compiler thực tế có API stubs và code generator cho target đó hay không.

### 5.2. Lệnh kiểm tra bắt buộc

```bash
java --version
javac --version
javac --help
```

Đọc mục `--release <release>` và dòng `Supported releases`. Trên một máy có **JDK 24.0.2** đã được kiểm thử, dòng help liệt kê:

```text
Supported releases:
8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24
```

Đây là **minh họa đầu ra của javac 24.0.2**, **không phải danh sách cho JDK 27 hoặc mọi build JDK**. Nếu hệ thống của bạn có Java 17/21/25/27, hãy chạy lại `javac --help` và dùng chính list nó in.

### 5.3. Lý do compiler không duy trì tất cả release từ Java 1.0

Hỗ trợ target cũ đòi hỏi:
- nhận diện phiên bản ngôn ngữ và cấu trúc source;
- tạo class files với format, attributes, bytecode rules tương thích;
- có tập API platform đúng release (signature data/ct.sym hoặc cách tương đương);
- kiểm thử compiler đối với các target được duy trì;
- duy trì chi phí bảo trì, bảo mật và tương thích.

**JEP 182 — Policy for Retiring javac -source and -target Options** mô tả chính sách rút dần hỗ trợ các mức source/target cũ. `--release` cũng chỉ được tài liệu hóa cho **limited previous releases**. Vì vậy, đừng hứa rằng một compiler 5–10 năm sau luôn còn build ra target Java 10.

### 5.4. Đọc class file cũ không đồng nghĩa tạo class file cũ

Oracle Migration Guide nói `javac` có thể **nhận và xử lý class files đã được tạo bởi những JDK rất cũ**, trong khi danh sách **target outputs** chỉ gồm tập limited previous releases.

Ví dụ:
- Compiler JDK 27 có thể đọc một JAR chứa classfile Java 8 khi nó nằm trên classpath, nếu hợp lệ và tương thích.
- Điều đó không chứng minh compiler JDK 27 còn phát mã cho **mọi** release từ Java 1 đến 27.
- Một dependency Java 8 có thể được dùng trong ứng dụng Java 17, nhưng cũng có thể chứa API runtime behavior không còn phù hợp; phải test.

Khái niệm **backward classfile reader** khác **cross-compiler target**.

### 5.5. Nếu `--release N` không được hỗ trợ thì làm gì?

Quy trình đúng:
1. Ghi lại `java --version`, `javac --version`, `javac --help` của CI.
2. Kiểm tra có **JDK/toolchain được tổ chức cho phép** nào hỗ trợ target cần thiết không.
3. Nếu target thật sự đã EOL, cân nhắc **nâng minimum supported runtime** và cập nhật hợp đồng sản phẩm thay vì đóng băng toolchain quá cũ.
4. Nếu bắt buộc duy trì compatibility vì hợp đồng/thiết bị nhúng, dùng **toolchain target-specific** trong môi trường build an toàn, cô lập theo chính sách bảo mật; **không** ép compiler mới chấp nhận một giá trị nó từ chối.
5. Dùng runtime tương ứng cho integration/compatibility tests và kiểm chứng external dependencies.
6. Ghi rõ quyết định trong CI/build scripts; tránh “đổi target xuống một số khác cho build xanh” khiến artifact không đúng hợp đồng.

Không tự bật cờ undocumented hoặc dựa vào internal compiler implementation để “khôi phục” một release đã bị bỏ.

## 6. Demo CLI Java 10: hai dòng lệnh chạy được

### 6.1. File `CompatHello.java`

Tạo file:

```java
import java.util.List;

public class CompatHello {
    public static void main(String[] args) {
        var names = List.copyOf(List.of("A", "B"));
        System.out.println(names);
    }
}
```

Source này cố tình chỉ dùng:
- `var` trong local declaration (Java 10);
- `List.copyOf` (Java 10);
- `List.of` (Java 9).

Không dùng bất kỳ syntax hay API đòi Java 11+.

### 6.2. Biên dịch với một compiler mới hơn có hỗ trợ Java 10

Trên Bash, PowerShell, CMD (cú pháp ở đây không cần shell-specific expansion):

```bash
javac --version
javac --help
javac --release 10 -d out CompatHello.java
java -cp out CompatHello
javap -verbose -classpath out CompatHello
```

**Stdout của `java -cp out CompatHello`:**

```text
[A, B]
```

Với `javap -verbose`, tìm:

```text
major version: 54
```

Đã kiểm tra thao tác biên dịch/chạy bằng `javac 24.0.2`; nhận stdout `[A, B]` và class major 54. Dòng `javac --version` và phần lớn output `javap` sẽ **khác theo build và chi tiết classfile**, nên không đóng đinh toàn bộ log.

### 6.3. Compile với `--release 9` sẽ không qua

```bash
javac --release 9 -d out CompatHello.java
```

Java 9 không có local type inference `var` hoặc `List.copyOf`, nên compilation thất bại. Ở compiler khác nhau, diagnostic có thể là lỗi cú pháp/không tìm thấy symbol/method hoặc nhiều lỗi đồng thời. **Không phụ thuộc chính xác tiếng Anh/đường dẫn/số dòng trong log lỗi** khi viết automated CI tests; chỉ kiểm tra exit status và quan sát nội dung chính.

**Không chạy output cũ trong `out` rồi tưởng compile vừa thành công.** Một compiler run FAIL có thể để lại class files từ build trước. Khi kiểm tra target, dùng output directory sạch hoặc toolchain build isolation.

### 6.4. Nếu `javac` báo “release version 10 not supported”

Điều đó chỉ nói **compiler đang chạy không hỗ trợ target 10**, không chứng minh:
- Java 10 từng không tồn tại;
- cú pháp `--release` bị loại khỏi mọi JDK;
- `List.copyOf` biến mất khỏi Java hiện đại;
- JVM không thể đọc class major 54.

Hãy xem danh sách `Supported releases` và chọn một **target thực tế được hỗ trợ**, dùng toolchain phù hợp nếu có yêu cầu hợp đồng đặc biệt.

### 6.5. Không khuyến nghị chạy JDK 10 như production runtime hiện nay

Lệnh demo `--release 10` giúp **học về nguồn gốc syntax/API của Java 10**. Để phát triển ứng dụng mới, nên xác định minimum runtime thực tế như **JDK 17/21/25 LTS** theo chính sách tổ chức, cập nhật security patches và kiểm thử. Không “đưa Java 10 vào production” chỉ để đảm bảo bài học khớp tên module.

## 7. Vì sao `-source/-target` kém chắc chắn hơn `--release`?

### 7.1. Cùng bytecode version nhưng khác API checks

Giả sử developer dùng compiler mới:

```bash
javac -source 10 -target 10 Example.java
```

Tùy compiler, câu lệnh có thể còn được hỗ trợ hoặc đã bị retire; nếu được hỗ trợ, nó **không đủ** để chứng minh các method nền tảng được tham chiếu đều có mặt trong Java 10. Thay vì phụ thuộc việc cài thêm bootclasspath/module system đúng release, Oracle khuyến nghị dùng:

```bash
javac --release 10 Example.java
```

Nếu compiler hỗ trợ target 10, cách này đặt **API level** cùng ngôn ngữ/bytecode level.

**Không cần dùng cả `-source`/`-target`/`--release` trên cùng một lệnh:** chúng là những option không thể kết hợp theo `javac` command spec.

### 7.2. Một bytecode major hợp lệ vẫn có thể nổ khi chạy

Ví dụ `-source 10 -target 10` có thể cho classfile major 54, nhưng source gọi một method **chỉ xuất hiện Java 11** vì compiler đã nhìn thấy API trên JDK 24. Runtime Java 10 khi load/resolve call có thể ném `NoSuchMethodError`. `--release 10` phát hiện lỗi nền tảng sớm khi compile.

**Ngoại lệ quan trọng:** `--release` chỉ kiểm chứng API có trong **platform signature** mà compiler mang theo, **không phải mọi use-case reflection/third-party JNI**. Một method trong dependency có thể liên kết tới class ra đời sau; Java Compiler không thay runtime test của toàn ứng dụng.

### 7.3. Không sử dụng `--add-exports` để phá API barrier

Theo Oracle `javac` docs, khi `--release` chọn một Java release có **module system**, `--add-exports` **không được phép** dùng để mở thêm các packages của Java SE/JDK/standard modules beyond exports được release định nghĩa. Internal JDK classes không phải API công khai ổn định.

Nếu một project phụ thuộc `jdk.internal.*` hoặc `sun.*`:
- tìm API public được hỗ trợ để thay thế;
- dùng `jdeps --jdk-internals` như bước phát hiện tĩnh;
- test runtime mạnh hơn cho reflection, MethodHandles và JNI;
- không giả định `--release` cho phép tiếp tục dùng internals bằng một cờ compiler.

JDK mới còn thay đổi mạnh encapsulation, nên việc loại bỏ các phụ thuộc internal càng quan trọng.

### 7.4. Ngữ nghĩa flags cho JDK 8 và JDK 9+ targets

Oracle javac manual đặt ra các ràng buộc:
- Với target **JDK 8 và trước đó**, module-system options không áp dụng vì module system chưa tồn tại.
- Với target **JDK 9+**, không cấu hình boot classpath kiểu JDK 8.
- Khi chọn `--release`, không tùy ý dùng các option thay platform classes hoặc mở internal APIs trái với release.

Thông điệp học tập: **không trộn những cơ chế cross-compilation của thời kỳ khác nhau vào một lệnh**. Chọn `--release` khi có thể và dựa vào help/docs của compiler hiện tại.

## 8. Lab đầy đủ: kiểm thử matrix source/API/bytecode bằng Java Compiler API

Lab này chứng minh `--release` qua **mã Java chạy được**, không yêu cầu cài Java 9/10/11 thật hoặc framework bên ngoài. Chương trình sử dụng **Java Compiler API (`javax.tools`)** của **full JDK** đang chạy để tạo một số source units trong memory, gọi `javac` với các release khác nhau, đọc class major từ `.class` thành công và xóa thư mục tạm sau mỗi test.

**Điều kiện chạy:**
- JDK **17+ có module `jdk.compiler`** (full JDK), không phải custom runtime đã bỏ compiler.
- `javac` của JDK đang chạy **vẫn hỗ trợ target 9, 10, 11, 17**. Điều này đã được xác minh trên **JDK 24.0.2**, nhưng **không được suy ra vĩnh viễn cho mọi future JDK**; hãy kiểm tra `javac --help`.
- Mã lab được biên dịch bằng JDK hiện hành **không dùng `--release 10` cho chính bản thân lab**, vì lab sử dụng `record`, `Stream.toList` và Java Compiler API theo Java 17+.
- Không cần Java 10 runtime; không cho phép quyền elevated hoặc sửa project repositories.
- Output dự kiến **18 dòng** dưới các điều kiện đã nêu; nội dung diagnostic compiler được giữ trong bộ thu riêng để không làm stdout thay đổi theo build và locale.

### 8.1. File `ReleaseMatrixLab.java`

```java
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

import java.io.IOException;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Locale;

public class ReleaseMatrixLab {
    record Outcome(boolean success, int major, long errors) {
    }

    // Source file trong RAM, không cần lưu mỗi snippet ra .java.
    static final class Source extends SimpleJavaFileObject {
        private final String code;

        Source(String name, String code) {
            super(URI.create(
                    "string:///" + name + Kind.SOURCE.extension),
                    Kind.SOURCE);
            this.code = code;
        }

        @Override
        public CharSequence getCharContent(
                boolean ignoreEncodingErrors) {
            return code;
        }
    }

    static Outcome compile(
            JavaCompiler javac,
            int release,
            String name,
            String code) throws IOException {

        Path dir = Files.createTempDirectory("release-matrix-");

        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();

        try (StandardJavaFileManager files =
                     javac.getStandardFileManager(
                             diagnostics,
                             Locale.ROOT,
                             StandardCharsets.UTF_8)) {

            List<String> options = List.of(
                    "--release", Integer.toString(release),
                    "-proc:none",
                    "-d", dir.toString());

            Boolean success = javac.getTask(
                    null, files, diagnostics, options, null,
                    List.of(new Source(name, code))).call();

            long errors = diagnostics.getDiagnostics().stream()
                    .filter(d ->
                            d.getKind() == Diagnostic.Kind.ERROR)
                    .count();

            int major = -1; // Không có class file hợp lệ khi fail.

            if (Boolean.TRUE.equals(success)) {
                byte[] bytes = Files.readAllBytes(
                        dir.resolve(name + ".class"));

                // Class-file layout: 0..3 magic, 4..5 minor,
                // 6..7 major (big-endian, unsigned bytes).
                major = ((bytes[6] & 255) << 8)
                        | (bytes[7] & 255);
            }

            return new Outcome(
                    Boolean.TRUE.equals(success), major, errors);

        } finally {
            // Chỉ xóa các file .class tạm do lab vừa sinh ra.
            try (var children = Files.list(dir)) {
                for (Path file : children.toList()) {
                    Files.deleteIfExists(file);
                }
            }
            Files.deleteIfExists(dir);
        }
    }

    public static void main(String[] args)
            throws Exception {

        JavaCompiler javac = ToolProvider
                .getSystemJavaCompiler();

        System.out.println(
                "javac compiler available: " + (javac != null));

        if (javac == null) {
            // Custom runtime image không có jdk.compiler.
            return;
        }

        String api10 =
                "import java.util.List; "
                + "class ApiTen { "
                + "static int n(){ "
                + "return List.copyOf(List.of(1,2)).size(); "
                + "} }";

        String api11 =
                "class ApiEleven { "
                + "static String f(){ "
                + "return \"a\".repeat(3); "
                + "} }";

        String var10 =
                "class VarTen { "
                + "static int f(){ "
                + "var s = \"hi\"; return s.length(); "
                + "} }";

        String record16 =
                "record Point(int x, int y) {}";

        Outcome a = compile(
                javac, 10, "ApiTen", api10);
        Outcome b = compile(
                javac, 9, "ApiTen", api10);

        Outcome c = compile(
                javac, 10, "ApiEleven", api11);
        Outcome d = compile(
                javac, 11, "ApiEleven", api11);

        Outcome e = compile(
                javac, 9, "VarTen", var10);
        Outcome f = compile(
                javac, 10, "VarTen", var10);

        Outcome g = compile(
                javac, 10, "Point", record16);
        Outcome h = compile(
                javac, 17, "Point", record16);

        System.out.println(
                "Java 10 List.copyOf accepted: "
                        + a.success());
        System.out.println(
                "Java 10 List.copyOf class major: "
                        + a.major());
        System.out.println(
                "Java 9 List.copyOf rejected: "
                        + (!b.success() && b.errors() > 0));
        System.out.println(
                "Java 10 String.repeat rejected: "
                        + (!c.success() && c.errors() > 0));
        System.out.println(
                "Java 11 String.repeat accepted: "
                        + d.success());
        System.out.println(
                "Java 11 String.repeat class major: "
                        + d.major());
        System.out.println(
                "Java 9 var rejected: "
                        + (!e.success() && e.errors() > 0));
        System.out.println(
                "Java 10 var accepted: "
                        + f.success());
        System.out.println(
                "Java 10 var class major: "
                        + f.major());
        System.out.println(
                "Java 10 record rejected: "
                        + (!g.success() && g.errors() > 0));
        System.out.println(
                "Java 17 record accepted: "
                        + h.success());
        System.out.println(
                "Java 17 record class major: "
                        + h.major());
        System.out.println(
                "classfile major 54 means Java 10: "
                        + (a.major() == 54 && f.major() == 54));
        System.out.println(
                "classfile major 55 means Java 11: "
                        + (d.major() == 55));
        System.out.println(
                "classfile major 61 means Java 17: "
                        + (h.major() == 61));

        System.out.println(
                "API and syntax checked against release: "
                        + (a.success() && !b.success()
                            && !c.success() && d.success()
                            && !e.success() && f.success()
                            && !g.success() && h.success()));

        System.out.println(
                "runtime compatibility still requires testing: true");
    }
}
```

### 8.2. Biên dịch và chạy lab

```bash
javac ReleaseMatrixLab.java
java ReleaseMatrixLab
```

Ở đây **lab chính sử dụng JDK 17+**, trong khi **các sub-compilations** thử nhiều `--release` thấp hơn. Nếu target 9/10/11/17 đã bị bỏ ở compiler mà bạn đang dùng, hãy chọn một JDK được hỗ trợ có dãy targets thích hợp, hoặc dùng lab sau khi nâng các target theo yêu cầu thực tế; không sửa kết quả thành “PASS” giả.

### 8.3. Stdout đúng 18 dòng trên JDK 24.0.2 đã kiểm thử

```text
javac compiler available: true
Java 10 List.copyOf accepted: true
Java 10 List.copyOf class major: 54
Java 9 List.copyOf rejected: true
Java 10 String.repeat rejected: true
Java 11 String.repeat accepted: true
Java 11 String.repeat class major: 55
Java 9 var rejected: true
Java 10 var accepted: true
Java 10 var class major: 54
Java 10 record rejected: true
Java 17 record accepted: true
Java 17 record class major: 61
classfile major 54 means Java 10: true
classfile major 55 means Java 11: true
classfile major 61 means Java 17: true
API and syntax checked against release: true
runtime compatibility still requires testing: true
```

Đã kiểm thử bằng **OpenJDK 24.0.2**: đủ **18 dòng stdout** đúng như trên. `DiagnosticCollector` dùng để xác nhận các trường hợp fail **có ít nhất một error** mà không in toàn bộ thông điệp lỗi compiler. Những compiler builds khác có thể wording diagnostics khác, nhưng `--release` phải giữ ý nghĩa chặn API/syntax không thuộc release.

### 8.4. Từng phép thử chứng minh điều gì?

| Test | Target | Kết quả | Điều chứng minh |
| --- | ---: | --- | --- |
| `ApiTen` với `List.copyOf` | 10 | PASS, major 54 | API Java 10 có mặt ở target 10 |
| `ApiTen` với `List.copyOf` | 9 | FAIL | API Java 10 không được giả định có trên 9 |
| `ApiEleven` với `String.repeat` | 10 | FAIL | API Java 11 bị chặn khi target 10 |
| `ApiEleven` với `String.repeat` | 11 | PASS, major 55 | API Java 11 được phép |
| `VarTen` với local `var` | 9 | FAIL | Syntax inference Java 10 không thuộc 9 |
| `VarTen` với local `var` | 10 | PASS, major 54 | Syntax inference Java 10 hợp lệ |
| `Point` dùng record | 10 | FAIL | Record chưa tồn tại ở Java 10 |
| `Point` dùng record | 17 | PASS, major 61 | Java 17 có record chuẩn |

Đây là **compilation tests**. Lab **không** khởi chạy bytecode vừa sinh trên Java 9/10/11 runtime, không kiểm thử network, GC, security providers hay dependencies. Nó cố tình tách điều compiler có thể chứng minh khỏi những việc cần runtime validation.

### 8.5. Vì sao đọc hai byte ở offsets 6–7?

Một class file hợp lệ bắt đầu bằng:
- offsets `0..3`: `CAFEBABE` (magic);
- offsets `4..5`: minor version;
- offsets `6..7`: **major version**.

Java code:
```java
int major = ((bytes[6] & 255) << 8)
          | (bytes[7] & 255);
```

Đây là **đoạn minh họa nằm trong method `compile` của lab**. Mã gốc đọc file sau khi compiler xác nhận PASS, không cố đọc class của test FAIL. Nó chỉ dùng hai byte major version; một verifier thực tế nên dùng `javap -verbose` hoặc library đọc classfile/bytecode được hỗ trợ thay vì tự viết parser đầy đủ.

### 8.6. Vì sao tắt annotation processing ở lab?

`-proc:none` giúp:
- Tránh processors tự động chạy tùy classpath/module path.
- Giảm nhiễu do generated sources và files.
- Cô lập đúng các checks của Java compiler/API level.

Trong project production có Lombok, MapStruct, framework processors hoặc generated code, **không** tắt annotation processing chỉ vì lab làm vậy. Bạn phải bảo đảm processors tương thích với build JDK và generated output target release; một annotation processor được chạy bằng build JDK có thể yêu cầu API/toolchain khác với chương trình đang được biên dịch.

## 9. Giới hạn: `--release` không thể bảo đảm tất cả runtime compatibility

### 9.1. Third-party dependencies

Giả sử ứng dụng dùng Java 17 target nhưng một dependency được build cho Java 21 (class major 65):
- Source code của bạn có thể hợp lệ Java 17.
- Dependency có thể không load được trên Java 17.
- `--release 17` không có nghĩa compiler tự **hạ** bytecode của dependency.
- Có thể compiler phát lỗi “bad class file” khi nó phải đọc class mới hơn giới hạn của toolchain/runtime, hoặc lỗi xuất hiện khi runtime load một dependency chỉ sử dụng gián tiếp.
- Phải kiểm tra **toàn bộ dependency graph**, bao gồm transitive JARs và runtime plugins.

Một dependency có class major phù hợp nhưng gọi API được thêm sau target vẫn có thể fail ở runtime do thiếu method/class, đặc biệt nếu tác giả thư viện không build/test đúng.

### 9.2. Reflection và dynamic loading

Mã:
```java
Class<?> clazz = Class.forName("com.example.SomePlugin");
```

Đây là đoạn minh họa trong method (không phải program đầy đủ). `javac` không thể biết chắc **tên class runtime nào** sẽ được tải từ chuỗi/hệ thống plugins, cũng không biết module exports/permissions trong deployment cụ thể.

Tương tự:
- reflection gọi method theo tên;
- MethodHandles và invokedynamic;
- generated bytecode của framework;
- JNI/native libraries;
- ServiceLoader/providers;
- Java agents và instrumentation;

cần compatibility tests ngoài `--release`.

### 9.3. OS, locale, timezone, security và data formats

Một build Java 17 có thể:
- chạy khác về timezone database khi JDK được cập nhật;
- dùng security provider hay TLS policies khác;
- gặp GC, encoding, networking và filesystem khác;
- có cấu hình module path/classpath khác;
- yêu cầu native library architecture không đúng host;
- gặp service responses/data sources mới.

`--release 17` không đóng băng **hành vi** của toàn nền tảng Java 17, không đảm bảo đã dùng đúng security patches, và không đảm bảo kết quả từ các dịch vụ bên ngoài.

### 9.4. Preview features không phải “compatibility target cũ”

Các preview language features có lifecycle riêng và thường yêu cầu cờ `--enable-preview` cùng release hiện hành của compiler theo tài liệu tương ứng. Không kỳ vọng có thể dùng **preview feature của JDK 25** mà tạo class binary hoàn toàn tương thích Java 17 chỉ bằng `--release 17`.

Nếu ứng dụng cần tương thích với một runtime LTS cũ, ưu tiên **tính năng chuẩn đã có tại target**. Tránh xây hợp đồng compatibility dựa trên preview syntax hoặc incubator APIs không thuộc target.

### 9.5. Multi-release JARs là trường hợp khác

**Multi-release JAR** có thể chứa classfile variants trong `META-INF/versions/N/` để runtime hỗ trợ lựa chọn implementation theo version. Đây là kỹ thuật packaging cần cấu hình đúng và test nhiều runtimes, **không** có nghĩa một lần `javac --release N` tự sinh mọi biến thể.

Nếu muốn một core Java 17 và implementation tối ưu Java 21:
- compile core với `--release 17`;
- compile variant với target Java 21 bằng toolchain hỗ trợ;
- package multi-release JAR đúng cấu trúc;
- chạy tests trên ít nhất Java 17 và 21+;
- không dựa vào JAR manifest/version folder mà bỏ qua binary/API verification.

Bài này chỉ giới thiệu ranh giới, không triển khai multi-release packaging hoàn chỉnh.

## 10. Tích hợp Maven — `maven.compiler.release`

### 10.1. Mẫu `pom.xml` phù hợp với JDK hiện đại

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>release-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.15.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Tài liệu Maven Compiler Plugin **3.15.0** (tháng 1/2026) hướng dẫn `maven.compiler.release`; dùng version mà tổ chức đã kiểm duyệt về compatibility/security. Nếu build JDK thực tế không hỗ trợ target 17 (không xảy ra với JDK 17+ có `--release 17` phù hợp), compile phải fail sớm thay vì tự chuyển target.

`maven.compiler.release=17` bảo đảm **target Java 17**. Nó **không** ép Maven đang chạy bằng **JDK 17**; hãy kiểm tra `mvn -version` và dùng toolchains hoặc CI image/runner để chọn JDK compiler.

### 10.2. Toolchain JDK khác minimum runtime

Một dự án có thể build với Maven chạy JDK 25 và đặt `maven.compiler.release=17`. Các plugins/annotation processors Maven có thể chạy trong JVM build, **không nhất thiết** chạy trong Java 17 runtime của sản phẩm.

Làm rõ trong CI:
- **JDK chạy Maven** là gì?
- **javac thực sự được Maven gọi** là version nào?
- **maven.compiler.release** là mấy?
- **JRE/JDK tối thiểu mà sản phẩm hỗ trợ** là mấy?
- **tests chạy trên runtime tối thiểu** có tồn tại không?

Không giả định maven property đồng nghĩa Maven compiler tự cài JDK 17 hoặc chạy toàn bộ test suite trên runtime 17.

### 10.3. Đừng trộn source/target với release

Một cấu hình POM chứa đồng thời:
```xml
<maven.compiler.release>17</maven.compiler.release>
<maven.compiler.source>11</maven.compiler.source>
<maven.compiler.target>11</maven.compiler.target>
```

có thể gây xung đột hoặc behavior phụ thuộc plugin/compiler. Trên dự án mới, chọn **một source of truth** cho minimum supported runtime và dùng `release` nhất quán; tách toolchain selection ra khỏi target release.

Tài liệu Maven 3.15.0 có những nhánh compatibility đặc biệt khi Maven chạy với JDK 8, nhưng không dùng chúng làm khuyến nghị chính cho dự án đang phát triển trên các JDK LTS hiện đại.

## 11. Tích hợp Gradle — toolchains và `options.release`

### 11.1. Kotlin DSL: build JDK 25, target Java 17

```kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(25)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release = 17
}
```

Đây là nội dung cấu hình **`build.gradle.kts`** — cần một project Gradle hợp lệ và Gradle version có hỗ trợ JDK 25 để chạy. Không tự giả định Gradle sẽ tải toolchain nếu môi trường không bật JDK provisioning/resolver.

- `toolchain.languageVersion=25`: dùng compiler/toolchain **Java 25**.
- `options.release=17`: source syntax, class target và platform API **Java 17**.
- Không cần đặt `sourceCompatibility=17`/`targetCompatibility=17` riêng để cố bắt chước `--release`.

### 11.2. Groovy DSL tương đương

```groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(25)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
```

Đây là **`build.gradle`** (Groovy DSL); không dùng code Groovy DSL trong `build.gradle.kts`. Gradle docs khuyến nghị toolchain để chọn JDK thực sự dùng biên dịch, và `options.release` để bảo đảm strict target compatibility.

### 11.3. Cần verify Gradle run thật

```bash
./gradlew --version
./gradlew clean compileJava
./gradlew test
```

Các lệnh minh họa Bash/macOS/Linux. Trên Windows CMD/PowerShell có thể dùng `gradlew.bat`. Không gọi đây là “lệnh JDK thuần” vì nó cần project Gradle, wrapper và plugins.

Kiểm tra outputs `build/classes/java/main` hoặc artifact Jar, dùng `javap -verbose`; test runtime trên **Java 17** nếu sản phẩm hứa hỗ trợ Java 17.

## 12. CI/CD: cấu hình build tốt chưa đủ, phải kiểm chứng artifact và runtime

### 12.1. Checklist thứ tự chuẩn

**Bước A — Xác định hợp đồng:**
- Minimum Java runtime thực sự được bảo trì và security-patched?
- Tối đa hỗ trợ runtime nào?
- Ứng dụng chạy trên classpath hay module path?
- Có dependencies/JNI/agents gây version-specific behavior?
- Có cần hỗ trợ multi-release JAR hoặc preview features không?

**Bước B — Build đáng tin:**
- Pin JDK distribution/build và Maven/Gradle version.
- `javac --help` phải có target release.
- Build bằng `--release MIN_JAVA`; dùng clean output directory.
- Pin dependencies/lockfiles, offline/reproducible build nếu chính sách yêu cầu.
- Tách main application sources khỏi code generated bởi processor nếu target khác nhau.

**Bước C — Kiểm tra binary:**
- Kiểm tra class major mọi classes của application/JAR.
- Kiểm tra dependencies và transitive JARs.
- Dùng `jdeps` khi phù hợp để tìm phụ thuộc JDK internal APIs hoặc module dependencies.
- Với multi-release JAR, kiểm tra class versions ở từng folder.
- Bật lint/build errors thích hợp thay vì nuốt warning về compatibility.

**Bước D — Runtime verification:**
- Chạy unit/integration tests trên minimum supported JDK.
- Chạy smoke tests trên JDK được triển khai production.
- Khi hỗ trợ nhiều JDK, test matrix từ min tới max theo rủi ro.
- Kiểm tra reflection, TLS, serialization, database drivers, native libraries và file encoding/timezone.
- Đánh giá performance/GC và security behavior trên runtime quan trọng.

**Bước E — Release:**
- Lưu JDK build, compiler flags, dependency manifest, artifact SHA.
- Chỉ publish nếu compile/tests và security scans đạt.
- Có canary/rollback theo môi trường.

### 12.2. Một ví dụ ma trận CI không phụ thuộc platform CI

| Pha | Build JDK | Release target | Runtime test | Tiêu chí |
| --- | --- | --- | --- | --- |
| Compile | JDK 25 | 17 | Chưa chạy | Build PASS, không dùng API Java 18+ |
| Minimum runtime | — | Artifact target 17 | JDK 17 cập nhật | Unit + integration PASS |
| Current LTS | — | Artifact target 17 | JDK 21/25 cập nhật | Smoke + compatibility PASS |
| Latest-feature check | — | Artifact target 17 | JDK 27 (nếu được hỗ trợ/thử nghiệm) | Phát hiện thay đổi behavior, không coi là thay LTS |

**Không buộc mọi product phải test mọi JDK** nếu hợp đồng chỉ hỗ trợ một JDK; matrix là ví dụ cách xác định coverage có chủ đích. JDK 10 không được đưa vào làm runtime production khuyến nghị.

### 12.3. Cách kiểm tra toàn JAR

Một JAR chứa nhiều classes có thể có classes do build plugin hoặc dependency shading tạo ra. **`javap` chỉ một main class chưa đủ** để kết luận mọi class version đều phù hợp.

Có thể:
1. Dùng `jar tf application.jar` để liệt kê class entries.
2. Dùng một công cụ bytecode được bảo trì, hoặc code kiểm tra mọi entry `.class` đọc major tại offset 6–7.
3. Báo class nào vượt target và fail CI.
4. Với multi-release JAR, áp policy riêng cho `META-INF/versions/N`; không báo false positive cho classes chỉ được dùng từ runtime version N tương ứng.
5. Kiểm tra cả dependencies trong final runtime classpath, không chỉ classes của artifact gốc.

**Class major không kiểm chứng platform APIs hoặc semantic behavior**, nên build bằng `--release` và runtime tests vẫn cần.

### 12.4. Có cần cài JDK cũ để cross-compile không?

Nếu compiler mới hỗ trợ target N, **`--release N` không cần bạn cài riêng JDK N chỉ để kiểm tra các public platform APIs**. JDK hiện hành mang thông tin signature cần thiết cho các release được hỗ trợ.

Tuy nhiên:
- Để **test runtime thực sự trên Java N**, bạn cần một runtime phù hợp được phép sử dụng.
- Với release đã EOL, bài này **không khuyên cài runtime cũ để phục vụ production**, vì yêu cầu bảo mật.
- Nếu compiler không hỗ trợ N, phải dùng supported toolchain/đổi hợp đồng; `--release` không tự tải SDK target từ internet.
- Với annotation processors hoặc classpath third-party, có thể cần build tooling riêng.

## 13. Các lỗi thường gặp và cách xử lý

| Lỗi / hiểu nhầm | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| “`--release` xuất hiện từ Java 10” | Feature ra đời ở JDK 9 / JEP 247 | Ghi đúng lịch sử, Java 10 chỉ là một target |
| “`--release 10` chạy trên mọi `javac` mới” | Compiler chỉ hỗ trợ limited previous releases | Chạy `javac --help` của compiler thực |
| “JDK 17 có thể `--release 25`” | Compiler không thể nhắm future release | Chọn build JDK 25+ |
| “`-source/-target` đủ để chặn API mới” | Không tự giới hạn platform API classes | Dùng `--release` |
| “Class major 54 thì mọi API chắc là Java 10” | Bytecode format và API linking là hai checks khác | Kiểm tra `--release 10` + runtime tests |
| “Một compiler đọc JAR Java 8 thì tạo được target mọi JDK” | Reader compatibility khác target support | Đọc danh sách Supported releases |
| “`--release 10` cho phép gọi `String.repeat`” | API Java 11 | Đổi API hoặc nâng minimum runtime |
| “Java 9 hỗ trợ `List.copyOf`” | API ra mắt Java 10 | `--release 9` phải từ chối |
| “`record` là Java 10 syntax” | Records chuẩn từ Java 16 | Dùng Java 16+ target |
| “`var` dùng được cho mọi field/parameter từ Java 10” | Local variable type inference có quy tắc giới hạn | Dùng đúng ngữ cảnh `var` |
| “Bật `--add-exports` để bypass `--release`” | javac không cho phá exports của release target | Loại JDK internals |
| “Chỉ cần chạy `javac` là tests tự chạy trên runtime cũ” | Compilation khác execution | Thiết lập test matrix runtime |
| “`--release` giảm version bytecode của dependencies” | Compiler không rewrite JARs | Chọn dependencies tương thích |
| “`--release` test được JNI/Reflection” | Dynamic linkage nằm ngoài static checks | Integration tests và native checks |
| “Maven property tự chọn JDK” | Toolchain selection khác target release | Cấu hình JDK/toolchains riêng |
| “Gradle sourceCompatibility bằng options.release” | API validation mạnh hơn ở `--release` | Dùng `options.release` |
| “JDK 27 còn mới nhất thì mọi API của nó an toàn cho Java 17” | API target 17 khác 27 | Giữ `--release 17` khi build |
| “Một class `javap` major 61 đủ kiểm tra all JAR” | Các classes khác có thể target mới hơn | Scan toàn artifact |
| “Compilation thành công chứng minh performance/bảo mật” | API/source checks không nói runtime security/behavior | Test, monitoring, canary |
| “Release 10 unsupported nên phải bỏ `--release`” | Toolchain không có target, không phải flag sai | Đổi toolchain/migration plan, không giảm guardrail |
| “Không cần dọn output giữa hai compile runs” | Stale classes tạo false success | Clean build hoặc isolated output directories |
| “JDK 10 còn phù hợp production vì javac target 10” | Khả năng cross-compile không liên quan support lifecycle | Dùng supported JVM/runtime |
| “`--enable-preview` cho phép preview mới chạy trên target cũ” | Preview theo release/compiler hiện hành | Không dựa preview khi yêu cầu old runtime |
| “JVM mới luôn hành xử như JVM cũ” | Behavioral compatibility khác binary | Test integration và SLO trên runtime |

## 14. Bài tập có đáp án

### Bài 1 — Lịch sử

**Đề:** `--release` được giới thiệu lần đầu trong JDK 10 hay JDK 9?

**Đáp án:** **JDK 9**, qua **JEP 247 — Compile for Older Platform Versions**. Module Java 10 dùng flag để kiểm tra features/API Java 10.

### Bài 2 — Ba ràng buộc

**Đề:** `javac --release 17` kiểm tra những thành phần gì?

**Đáp án:** Ngữ pháp/tính năng ngôn ngữ Java 17, class file format cho release 17 và tập platform API được phép dùng của Java 17 (gồm Java SE + exported JDK APIs tương ứng).

### Bài 3 — Java 10 classfile

**Đề:** Classfile major sau compile `--release 10` thường là bao nhiêu?

**Đáp án:** **54**. Có thể xem bằng `javap -verbose` hoặc đọc header bytecode.

### Bài 4 — Java 17 classfile

**Đề:** Compiler JDK 25 build `--release 17`, classfile major là gì?

**Đáp án:** **61**, không phải 69. Java 25 là **build JDK**, 17 là target.

### Bài 5 — API Java 10

**Đề:** Vì sao `List.copyOf(List.of(1))` không được chấp nhận với `--release 9`?

**Đáp án:** `List.of` có từ Java 9, nhưng `List.copyOf` chỉ có từ Java 10. `--release 9` chặn API hậu Java 9.

### Bài 6 — API Java 11

**Đề:** `"a".repeat(3)` được chấp nhận với `--release 10` không?

**Đáp án:** Không; `String.repeat` được thêm vào **Java 11**. Dùng `--release 11` hoặc triển khai cách xử lý compatible với Java 10 nếu thật sự cần target cũ.

### Bài 7 — Source Java 10

**Đề:** `var s="hello";` có hợp lệ trong local declaration với `--release 9`?

**Đáp án:** Không như Java 10 local variable inference. `var` được thêm như restricted type name cho local inference ở Java 10.

### Bài 8 — Records

**Đề:** Vì sao `record Point(int x,int y) {}` không biên dịch với `--release 10`?

**Đáp án:** Record được chuẩn hóa sau Java 10 (Java 16). `--release 17` chấp nhận record chuẩn.

### Bài 9 — Compiler quá cũ

**Đề:** Cài `javac 17` thì có thể `--release 25` không?

**Đáp án:** Không. Compiler JDK17 không phát mã cho Java25 target. Dùng JDK25+ nếu target thực sự là Java25.

### Bài 10 — Compiler quá mới

**Đề:** Một compiler JDK trong tương lai không còn hỗ trợ `--release 10`. Có nên bỏ flag và chỉ `-target 10` để “đỡ lỗi” không?

**Đáp án:** Không. Đó là cách làm mất API compatibility guardrail. Chọn toolchain hỗ trợ target hoặc nâng minimum runtime theo kế hoạch.

### Bài 11 — Runtime cũ đọc class mới

**Đề:** Một classfile major 61 được load bởi JVM 11. Kết quả?

**Đáp án:** JVM11 không hỗ trợ classfile Java17, thường ném `UnsupportedClassVersionError`. Phải dùng runtime Java17+ hoặc compile lại cho target phù hợp với source/API.

### Bài 12 — Class major không chứng minh API-level

**Đề:** `-source 10 -target 10` phát major 54 nhưng source dùng Java11 API. Có chắc chạy trên Java10?

**Đáp án:** Không. Có thể phát sinh `NoSuchMethodError`/`NoClassDefFoundError`. Dùng `--release 10` để bắt lỗi platform API ngay khi compile, và runtime tests cho integration.

### Bài 13 — Dependency cấp cao hơn

**Đề:** Ứng dụng target Java17, thư viện bên thứ ba có class major65. `--release 17` tự hạ nó xuống major61?

**Đáp án:** Không. Phải chọn dependency build cho Java17 hoặc phiên bản thư viện tương ứng, scan runtime artifacts và test linkage.

### Bài 14 — Reflection

**Đề:** Mã `Class.forName(configValue)` có được `--release` đảm bảo mọi plugin runtime tồn tại không?

**Đáp án:** Không. Class names được xác định runtime, cần integration tests với plugin packages, classpath và security policy thực tế.

### Bài 15 — Kiểm tra version hỗ trợ

**Đề:** Tại sao không hardcode “mọi javac 27 đều hỗ trợ 1–27”?

**Đáp án:** Oracle javac manual quy định current + **limited number of previous releases**. Danh sách cụ thể lấy từ `javac --help`, không từ tuổi lịch sử của Java.

### Bài 16 — Maven

**Đề:** POM có `<maven.compiler.release>17</maven.compiler.release>` nhưng Maven chạy JDK25. Artifact target nào?

**Đáp án:** Nếu compiler hỗ trợ option, target Java17. Maven chạy JDK25 không làm target tự đổi sang25; phải xác nhận compiler/toolchain thật và test trên Java17.

### Bài 17 — Gradle toolchains

**Đề:** Gradle đặt `languageVersion=25` và `options.release=17`. Hai số có vai trò khác nhau?

**Đáp án:** 25 chọn build JDK/toolchain; 17 hạn chế Java source/API/classfile target. Dự án cần Gradle version hỗ trợ JDK25 và runtime tests trên Java17.

### Bài 18 — CI runtime matrix

**Đề:** Build Java17 target PASS trên JDK25. Có cần chạy test bằng Java17 không nếu hợp đồng hỗ trợ Java17?

**Đáp án:** Có. Compile không kiểm chứng mọi runtime behavior, dependencies, security/OS hoặc dynamic loading.

### Bài 19 — Preview

**Đề:** Có thể bật `--enable-preview` trên JDK25 rồi `--release 17` để dùng preview syntax mới trong app Java17 không?

**Đáp án:** Không thể dùng preview language features của build JDK mới như thể chúng là tính năng chuẩn ở target cũ. Cần chọn source không dùng preview hoặc nâng minimum runtime.

### Bài 20 — Mục tiêu hiện đại

**Đề:** Tại sao nên dùng `--release 17/21/25` theo hợp đồng sản phẩm hơn là cố chạy Java10 runtime chỉ vì đang học Java10?

**Đáp án:** Cross-compilation là kỹ thuật compatibility; runtime Java10 đã hết vòng cập nhật phổ biến. Sản phẩm nên sử dụng JDK được hỗ trợ/được cập nhật bảo mật và target phù hợp SLO, dependencies và khách hàng thực tế.

## 15. Checklist kiểm chứng bài và dự án

- [ ] Phân biệt bản Java 10 trong tên module với Java runtime production hiện nay.
- [ ] Ghi đúng lịch sử: JEP 247 và `--release` bắt đầu từ JDK9.
- [ ] Không mặc định compiler nào cũng hỗ trợ target Java10 hoặc mọi release lịch sử.
- [ ] Chạy `java --version`, `javac --version`, `javac --help` ở build runner thật.
- [ ] Chỉ dùng target N có trong `Supported releases` của `javac`.
- [ ] Dùng `--release` thay cho `-source/-target` khi cross-compiling trên JDK9+.
- [ ] Không trộn `--release` cùng `-source`, `-target` hoặc flags phá platform encapsulation.
- [ ] Chọn target theo minimum supported **runtime**, không theo phiên bản JDK mới nhất trên laptop.
- [ ] Hiểu `--release` kiểm tra language rules, platform APIs và classfile version cùng nhau.
- [ ] Hiểu `var` và `List.copyOf` thuộc Java10; `String.repeat` Java11; records chuẩn Java16.
- [ ] Dùng `javap -verbose` hoặc scan classfile header để kiểm major 54/55/61/... phù hợp target.
- [ ] Không gọi major version check là bằng chứng tổng runtime compatibility.
- [ ] Kiểm tra transitive dependencies, annotation processors, generated code và JNI.
- [ ] Dùng `jdeps --jdk-internals` để phát hiện một số JDK internal dependencies (không phải quét được mọi reflection).
- [ ] Với Maven, dùng `maven.compiler.release` và ghi toolchain/JDK compiler thật.
- [ ] Với Gradle, phân biệt `toolchain.languageVersion` và `options.release`.
- [ ] Clean output trước khi test compile failed; tránh stale classfiles.
- [ ] Chạy unit/integration/smoke tests trên minimum supported runtime.
- [ ] Nếu runtime đã EOL, lên kế hoạch nâng target thay vì ép build cũ không an toàn.
- [ ] Không dùng preview features mới để vượt compiler target cũ.
- [ ] Chạy `CompatHello.java` với `--release 10` trên compiler hỗ trợ và kiểm output `[A, B]` + major54.
- [ ] Chạy `ReleaseMatrixLab.java` với full JDK hỗ trợ 9/10/11/17; đối chiếu đủ **18 dòng stdout** trên JDK24.0.2.
- [ ] Chỉ publish artifact sau khi compiler compatibility và runtime verification cùng PASS.

## 16. Kết luận

**`javac --release N` là hợp đồng biên dịch ba lớp:** source language level, class file target và nền tảng API tương ứng release N. Nhờ đó, một JDK mới có thể xây ứng dụng cho một **runtime cũ hơn mà compiler vẫn hỗ trợ** mà không vô tình gọi API mới. Trong ví dụ của module Java 10, `--release 10` chấp nhận `var`/`List.copyOf`, còn `--release 9` không; `--release 10` từ chối `String.repeat` của Java11 và `record` của Java16.

Nhưng `--release` **không có danh sách target bất biến**. Hãy **đọc `javac --help` của chính build JDK** để biết supported releases, thay vì suy đoán theo số năm. Nó cũng **không kiểm thử được** thư viện thứ ba, reflection, JNI, behavior, operating system hoặc production dependencies; cần CI runtime tests tương ứng. Khi target hết được compiler hoặc nhà cung cấp hỗ trợ, hãy **chọn toolchain được quản trị hoặc nâng minimum runtime**, không bỏ compatibility checks để build xanh.

Đó là cách sử dụng `--release` phù hợp với **JDK được cập nhật hiện nay**, tránh biến những ví dụ lịch sử về Java 10 thành lời khuyên triển khai legacy runtime.

## 17. Tài liệu tham khảo và nguồn chuẩn

- [Oracle Java SE 27 — The javac Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javac.html): `--release`, supported previous releases, API platform, `--source`/`--target`, restrictions.
- [Oracle Java SE 27 — Preparing for Migration](https://docs.oracle.com/en/java/javase/27/migrate/preparing-migration.html): khuyến nghị `--release` và giới hạn target values, compatibility risk.
- [OpenJDK JEP 247 — Compile for Older Platform Versions](https://openjdk.org/jeps/247): lý do xuất hiện `--release` từ JDK 9, API signatures cho target.
- [OpenJDK JEP 182 — Policy for Retiring javac -source and -target Options](https://openjdk.org/jeps/182): chính sách về compiler support khi cũ dần.
- [Oracle Java SE 27 — javap Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javap.html): `-verbose`, xem major version/classfile details.
- [Java Virtual Machine Specification — Class File Format](https://docs.oracle.com/javase/specs/jvms/se27/html/jvms-4.html): magic/minor/major version, bytecode compatibility.
- [Oracle Java SE 25 — javax.tools.JavaCompiler](https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/tools/JavaCompiler.html): public Java Compiler API dùng trong lab.
- [OpenJDK JEP 286 — Local-Variable Type Inference](https://openjdk.org/jeps/286): `var` Java10.
- [Oracle Java SE 10 — List.copyOf](https://docs.oracle.com/javase/10/docs/api/java/util/List.html#copyOf(java.util.Collection)): API immutable copy của Java10.
- [Oracle Java SE 11 — String.repeat](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/String.html#repeat(int)): API mới ở Java11.
- [OpenJDK JEP 395 — Records](https://openjdk.org/jeps/395): record trở thành tính năng chuẩn từ Java16.
- [Apache Maven Compiler Plugin 3.15.0 — Setting the --release](https://maven.apache.org/components/plugins/maven-compiler-plugin/examples/set-compiler-release.html): `maven.compiler.release` và caveats của Maven builds.
- [Gradle — JVM Toolchains](https://docs.gradle.org/current/userguide/toolchains.html): cấu hình compiler JDK, `options.release` và strict cross compilation.
- [Gradle — Building Java and JVM Projects](https://docs.gradle.org/current/userguide/building_java_projects.html): khác biệt `sourceCompatibility`/`targetCompatibility` và `options.release`.