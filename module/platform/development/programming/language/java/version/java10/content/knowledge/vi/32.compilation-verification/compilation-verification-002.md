# Biên dịch tính năng Java 10 với phiên bản nguồn phù hợp

## 1. Mục tiêu và kết luận quan trọng

Khi viết ứng dụng có sử dụng **tính năng ngôn ngữ hoặc API được đưa vào Java 10**, cần cấu hình **compiler** sao cho mã nguồn được kiểm tra theo đúng phiên bản Java định hỗ trợ, tạo **class files** phù hợp và không vô tình gọi các API chỉ tồn tại ở JDK mới hơn.

**Cấu hình nên ưu tiên cho mã nguồn hướng tới Java 10, khi compiler hiện tại hỗ trợ release 10:**

~~~bash
javac --release 10 -encoding UTF-8 -d out10 SourceTenDemo.java
~~~

Ý nghĩa của `--release 10` theo tài liệu `javac` hiện hành:

1. **Ngữ pháp và quy tắc ngôn ngữ** tương ứng Java SE 10.
2. **Định dạng bytecode/class file** có target Java 10 (**major version 54**).
3. **Bề mặt Java SE và JDK platform APIs** khả dụng cho release 10, tránh gọi nhầm API chỉ xuất hiện trong JDK 11 trở lên.

**Không coi `-source 10 -target 10` là tương đương với `--release 10`.** Hai tùy chọn cũ chỉ ràng buộc ngôn ngữ và mục tiêu bytecode; nếu dùng JDK mới để compile, chúng có thể vẫn cho phép gọi API Java mới mà JVM Java 10 không có. Đây là một nguyên nhân của `NoSuchMethodError` hoặc `NoClassDefFoundError` khi triển khai.

**Không có nghĩa phải cài JDK 10 để chạy `javac --release 10`.** Một JDK mới hơn có thể biên dịch nhắm đến Java 10 **nếu** release này còn thuộc các giá trị nó hỗ trợ. Trên JDK 24.0.2 được kiểm thử, `--release 10` hoạt động. Với JDK khác, xem `javac --help` thay vì giả định mọi bản phát hành tương lai đều giữ mọi target cũ.

Mục tiêu bài học: hiểu chính xác cách chọn source/release, phân biệt **compiler JDK**, **language level**, **target bytecode**, **API level**, **runtime JDK**, kiểm thử `var` của Java 10 và cấu hình Maven/Gradle hiện hành.

## 2. Năm khái niệm phiên bản phải tách biệt

Giả sử máy build có JDK 24, code sử dụng `var` và mong muốn ứng dụng chạy được trên JVM Java 10.

| Khái niệm | Câu hỏi thực tế | Ví dụ |
| --- | --- | --- |
| **Compiler JDK** | `javac` thực sự được gọi từ JDK nào? | JDK 24 |
| **Source/language level** | Các cấu trúc cú pháp của release nào hợp lệ? | Java 10 |
| **Target class-file level** | `.class` có major version tương thích JVM nào? | Major **54** |
| **Platform API level** | Compiler cho phép gọi những lớp/phương thức JDK của release nào? | Java 10 với `--release 10` |
| **Runtime JDK** | JVM nào thật sự tải và chạy ứng dụng? | JVM 10 hoặc JVM mới hơn tương thích |

**Sai lầm thường gặp:** thấy `major version: 54` rồi tuyên bố mọi API trong chương trình “chắc chắn chạy được ở Java 10”. **Class-file version chỉ giải quyết một phần tương thích**; vẫn cần kiểm soát Java platform APIs, thư viện bên thứ ba, module boundaries và hành vi runtime.

Sơ đồ:

~~~text
Machine build: JDK 24
        |
        v
javac --release 10
        |
        +-- Java 10 language rules
        +-- Java 10 platform API surface
        +-- class file major version 54
        |
        v
SourceTenDemo.class
        |
        +-- JVM 10: class format có thể đọc được
        +-- JVM 11, 17, 21, 24, 26: class format thường được hỗ trợ
        |
        v
Thực tế chạy còn phụ thuộc thư viện, APIs và môi trường
~~~

JDK mới thường hỗ trợ bytecode của JDK cũ, nhưng **đừng biến sơ đồ thành bảo đảm mọi ứng dụng Java 10 hoạt động không đổi trên mọi JVM mới**: thư viện, system properties, native code, phản chiếu, security policies và môi trường vẫn có thể tạo khác biệt.

## 3. Java 10 bổ sung những gì quan trọng cho bài compile này?

### 3.1. `var` cho biến cục bộ (JEP 286)

Java 10 đưa **Local-Variable Type Inference** vào ngôn ngữ. Có thể viết:

~~~java
var title = "Java 10";
var count = 3;
var names = new java.util.ArrayList<String>();
~~~

Compiler suy ra **kiểu tĩnh tại compile time** từ biểu thức khởi tạo. `var` **không phải dynamic typing** và không biến Java thành một ngôn ngữ chạy không kiểm tra kiểu.

Ví dụ, biến `title` ở trên có kiểu `String`, không thể tùy tiện gán một đối tượng `Integer` khác kiểu vào sau đó.

Theo tài liệu Java hiện hành, `var` là **restricted type name**, không phải Java keyword tổng quát. Nó có những vị trí được phép và không được phép.

### 3.2. Các vị trí `var` dùng được trong Java 10

~~~java
// Biến cục bộ có initializer
var amount = 100;

// Biến điều khiển vòng for truyền thống
for (var i = 0; i < 3; i++) {
    System.out.println(i);
}

// Biến của enhanced for
for (var item : java.util.List.of("A", "B")) {
    System.out.println(item);
}
~~~

Có thể dùng `var` ở một số vị trí local khác với initializer, chẳng hạn tài nguyên trong `try-with-resources` theo ngữ nghĩa hỗ trợ của Java 10.

### 3.3. Các vị trí không hợp lệ đối với `var` ở Java 10

~~~java
// KHÔNG phải khai báo hợp lệ:
var field = "x";                  // field của lớp
var compute() { return 1; }      // kiểu trả về phương thức
void take(var param) { }         // tham số phương thức
var missing;                      // thiếu initializer
var unknown = null;              // không đủ kiểu để suy ra
~~~

Đây là **các đoạn phản ví dụ có chủ ý**, không phải code để ghép vào chương trình biên dịch thành công.

### 3.4. `var` trong tham số lambda là tính năng Java 11, không phải Java 10

Cú pháp:

~~~java
java.util.function.Function<String, Integer> length =
        (var text) -> text.length();
~~~

được hỗ trợ từ **Java 11 theo JEP 323**, **không phải Java 10**. Vì thế `javac --release 10` phải từ chối cú pháp này, còn `javac --release 11` có thể biên dịch.

**Không được nhầm mọi cách dùng `var` đều xuất hiện ở Java 10 chỉ vì JEP 286 được phát hành năm đó.** Dùng `--release 10` để tự động phát hiện ranh giới này.

## 4. API mới Java 10 cũng thuộc yêu cầu tương thích

Ngoài cú pháp, Java 10 còn có những API mà bài compile cần minh họa:

~~~java
var snapshot = java.util.List.copyOf(source);
var selected = java.util.Optional.of("ready").orElseThrow();
~~~

- `List.copyOf(Collection)`: từ **Java 10**, tạo `List` không thể thay đổi qua các mutator của `List`, không nhận phần tử `null`.
- `Optional.orElseThrow()` không có tham số: từ **Java 10**, lấy giá trị nếu có, nếu không ném `NoSuchElementException`.

Ngược lại:

~~~java
"   ".isBlank();
~~~

là API **String.isBlank() từ Java 11**. Nếu biên dịch nhắm đến Java 10, compiler phải phát hiện không có API đó.

Điểm này cho thấy bài học **không chỉ cần khóa cú pháp `var`**. Một chương trình không sử dụng bất kỳ cú pháp Java 11 nào vẫn có thể gọi nhầm **API Java 11** và gây lỗi trên runtime Java 10.

## 5. `javac --release 10`: lựa chọn phù hợp nhất

Lệnh:

~~~bash
javac --release 10 -encoding UTF-8 -d out10 SourceTenDemo.java
~~~

đưa ra ba loại ràng buộc đồng thời:

- **Language**: cú pháp Java 10 và các tính năng đã có trước đó.
- **Class-file target**: phát hành bytecode cho Java 10.
- **Java platform APIs**: chỉ sử dụng API của Java SE/JDK được định nghĩa và xuất ra theo release 10.

Tài liệu `javac` của Oracle Java SE 26 nêu rõ các API được kiểm tra theo release chỉ định; `--release` **không cho phép dùng tùy chọn phá encapsulation để truy cập các JDK internal packages không được export trong release đích**.

### Kiểm tra compiler có hỗ trợ `--release 10` hay không

~~~bash
javac -version
javac --help
~~~

Tìm dòng **Supported releases** trong output `--help`. Với JDK 24.0.2 trong môi trường kiểm thử, release 10 được hỗ trợ.

**Không mặc định rằng target “10” chắc chắn được mọi `javac` đời mới hỗ trợ mãi mãi.** Tài liệu Java SE 26 nói compiler hiện hành hỗ trợ release hiện tại và **một số release trước đó**, danh sách cụ thể lấy từ command-line help.

### Tại sao không dùng `-source 1.10`?

Từ Java 9, các phiên bản phát hành được ghi theo số như **9, 10, 11, 17**. Cấu hình hiện hành nên là:

~~~text
--release 10
~~~

Không sử dụng các string version cũ hay công thức tự chế kiểu `1.10` để nhắm đến Java 10. Những cú pháp phiên bản trước Java 9 không phải hướng dẫn phù hợp cho release này.

### Không trộn với `--source` hoặc `--target`

~~~bash
javac --release 10 --source 10 SourceTenDemo.java
~~~

Với `javac` hiện hành, đây là **lỗi tùy chọn**: `--release` không được dùng cùng `--source` hoặc `--target`.

Chọn **một cách**:

~~~text
Ưu tiên:
    --release 10

Chỉ khi có lý do đặc biệt, dùng:
    --source 10 --target 10
    + ràng buộc đúng Java 10 platform libraries
~~~

Nếu có `--release 10` thì không cần và không được thêm `--target 10` chỉ để “chắc chắn bytecode đúng”.

## 6. So sánh `--release 10` với `--source 10 --target 10`

| Tính năng | `--release 10` | `--source 10 --target 10` |
| --- | --- | --- |
| Chỉ chấp nhận cú pháp Java 10 trở xuống | Có | Có |
| Tạo class-file target Java 10 | Có | Có |
| Giới hạn Java SE/JDK API theo release 10 | **Có** | **Không đủ bảo đảm**, nếu dùng platform API mới |
| Ngăn `String.isBlank()` từ Java 11 | **Có** | Không nếu compiler đang dùng APIs của JDK mới |
| Phù hợp cross-compilation hiện hành | **Khuyến nghị** | Chỉ dùng khi có nhu cầu riêng và kiểm soát platform libraries |
| Cần `--source`/`--target` đi kèm | Không, thậm chí xung đột | Hai flag xác định hai trục riêng |
| Ngăn mọi thư viện bên thứ ba không tương thích | **Không** | Không |
| Tự kiểm thử trên JVM 10 thật | **Không** | Không |

### Cơ chế “API leak” khi chỉ đặt source/target

Giả sử compile trên JDK 24 và dùng `String.isBlank()` (Java 11):

~~~java
public final class ApiElevenDemo {
    public static void main(String[] args) {
        var text = "   ";
        System.out.println("blank=" + text.isBlank());
    }
}
~~~

- `javac --release 10 ApiElevenDemo.java`: **không biên dịch**, vì platform API Java 10 không có `String.isBlank()`.
- `javac --source 10 --target 10 ApiElevenDemo.java` trên JDK 24: **có thể biên dịch thành công**, vì source Java 10 cho phép `var`, còn compiler có thể nhìn thấy `String.isBlank()` từ platform libraries của JDK 24.
- Class file từ cách thứ hai vẫn có **major version 54**.
- Chạy trên **JDK 24**, nó in `blank=true`.
- Chạy trên **JVM Java 10 thực sự** mà mã đi đến lời gọi `String.isBlank()`, phương thức không có, dẫn đến lỗi linkage điển hình như `NoSuchMethodError`.

**Đã kiểm thử phần compile trên JDK 24.0.2 và chạy trên chính JDK 24. Không có JVM 10 trong phép thử, nên lỗi runtime trên Java 10 được giải thích bằng sự khác biệt API/linkage, không giả vờ đã quan sát trực tiếp lỗi từ JDK 10.**

`javac` cũng đưa cảnh báo khi dùng source 10 mà **không chỉ định đúng system modules/platform classes**: có nguy cơ tạo class files không chạy đúng JDK 10.

Với Java 9+ module system, tùy trường hợp có thể cung cấp bộ platform classes phù hợp cho `--source`/`--target` qua `--system`, nhưng **`--release` đơn giản và ít sai hơn** khi mục tiêu chỉ là tương thích Java 10.

## 7. Ví dụ Java 10 hoàn chỉnh, biên dịch và chạy được

Lưu tệp **`SourceTenDemo.java`** với nội dung:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

public final class SourceTenDemo {

    public static void main(String[] args) {
        // Java 10: local-variable type inference.
        var source = new ArrayList<String>();
        source.add("Java");
        source.add("10");

        // Java 10 API: unmodifiable snapshot.
        var snapshot = List.copyOf(source);

        // Thay đổi source không thay đổi phần tử trong snapshot.
        source.set(0, "Changed");

        var chars = 0;
        for (var word : snapshot) {
            chars += word.length();
        }

        // Java 10 API: no-arg Optional.orElseThrow().
        var selected = Optional.of("ready").orElseThrow();

        System.out.println(
                "snapshot=" + String.join(" ", snapshot));
        System.out.println("chars=" + chars);
        System.out.println("optional=" + selected);
        System.out.println("elements=" + snapshot.size());
    }
}
~~~

### Bước 1 — tạo thư mục đầu ra

~~~bash
mkdir out10
~~~

Lệnh trên phù hợp trong bash/zsh và PowerShell khi thư mục chưa tồn tại. `javac -d` nên trỏ đến thư mục output thích hợp đã chuẩn bị.

### Bước 2 — biên dịch bằng compiler mới có hỗ trợ release 10

~~~bash
javac --release 10 -encoding UTF-8 -d out10 SourceTenDemo.java
~~~

**Kết quả mong đợi:** biên dịch thành công, file `out10/SourceTenDemo.class` được tạo. `-encoding UTF-8` giúp source encoding ổn định ở các máy/CI. Code minh họa này chỉ dùng ASCII trong string literals, nhưng với code Việt hóa cần khai báo encoding rõ ràng.

### Bước 3 — chạy bằng JVM đang cài

~~~bash
java -cp out10 SourceTenDemo
~~~

**`stdout` đã được kiểm thử thực tế trên JDK 24.0.2:**

~~~text
snapshot=Java 10
chars=6
optional=ready
elements=2
~~~

Giải thích:

1. `List.copyOf(source)` tạo một danh sách không thể thay đổi qua các mutators của chính nó; `source.set(0, ...)` sau đó không làm `snapshot` đổi từ "Java" thành "Changed".
2. `chars=6` vì `"Java".length()==4` và `"10".length()==2`. Đây là số UTF-16 code units; trong dữ liệu ASCII thì trùng số ký tự nhìn thấy.
3. `Optional.of("ready").orElseThrow()` trả về `ready`.
4. `snapshot.size()==2`.

**Không khẳng định ví dụ đã chạy trên một JVM Java 10 thật:** thí nghiệm được thực hiện với **compiler và runtime JDK 24**. Lệnh `--release 10` tạo output nhắm Java 10; yêu cầu tương thích chặt cần thêm bước integration test trên runtime đích.

### Bước 4 — kiểm tra class-file version

~~~bash
javap -verbose -classpath out10 SourceTenDemo
~~~

Tìm dòng:

~~~text
major version: 54
~~~

**Đã kiểm thử trực tiếp:** lệnh trên cho **major version 54** sau khi `javac --release 10` biên dịch.

Theo Java Virtual Machine Specification **Java SE 26**, Java 10 gắn với **class file major 54**; Java 11 tương ứng 55, Java 17 là 61, Java 21 là 65, Java 24 là 68 và Java 26 là 70.

**Cảnh báo:** file `.class` phiên bản 54 có thể chứa lời gọi một API chỉ có ở Java 11 nếu bạn chỉ dùng `-source/-target`. Vì vậy **kiểm tra major version không đủ để chứng minh tương thích API**; dùng `--release` và kiểm thử runtime đích.

## 8. Test âm tính: `--release 9` phải từ chối mã Java 10

Thử với chính `SourceTenDemo.java`:

~~~bash
javac --release 9 SourceTenDemo.java
~~~

Trên JDK 24.0.2 được kiểm thử, compiler **trả lỗi**. Các nguyên nhân bao gồm:

- Dùng `var` trong local declarations, cú pháp mới từ Java 10.
- Gọi `List.copyOf` và `Optional.orElseThrow()` (không tham số), APIs mới từ Java 10.

Tùy JDK/compiler, diagnostic có thể là warning về `var` được xem như type name trong ngữ cảnh Java 9, sau đó lỗi `cannot find symbol`; **không sao chép một log tuyệt đối duy nhất** để mọi phiên bản compiler phải in giống nhau. Điều chắc chắn cần test là **exit code khác 0**.

### Vì sao test này có giá trị?

Nó xác nhận rằng code thật sự phụ thuộc vào **mốc Java 10**. Nếu chương trình cũng compile thành công với `--release 9`, có thể source của bạn chỉ dùng tính năng cũ hơn (điều đó không sai, nhưng không chứng minh Java 10 là release tối thiểu cần thiết).

Mặt khác, khi đang target Java 10 mà vô tình dùng cú pháp Java 11, `--release 10` sẽ chặn từ thời điểm biên dịch.

## 9. Test âm tính: API Java 11 không được lọt vào release 10

Lưu **`ApiElevenDemo.java`**:

~~~java
public final class ApiElevenDemo {

    public static void main(String[] args) {
        var text = "   ";
        System.out.println("blank=" + text.isBlank());
    }
}
~~~

**Dùng cách đúng:**

~~~bash
javac --release 10 ApiElevenDemo.java
~~~

**Kết quả mong đợi:** compiler từ chối vì không tìm thấy phương thức `String.isBlank()` trong API Java 10.

**Dùng cách thiếu ràng buộc API:**

~~~bash
mkdir outLeak
javac --source 10 --target 10 -d outLeak ApiElevenDemo.java
~~~

Trên JDK 24.0.2, cách thứ hai **biên dịch thành công** với warning về system modules. Kiểm tra:

~~~bash
javap -verbose -classpath outLeak ApiElevenDemo
~~~

thấy:

~~~text
major version: 54
~~~

Khi chạy **JDK 24**:

~~~bash
java -cp outLeak ApiElevenDemo
~~~

thu được:

~~~text
blank=true
~~~

**Bài học:** compiler chấp nhận source syntax Java 10 và tạo class-file version 54, nhưng **không khóa platform API**. Nếu deploy bytecode ấy lên JVM Java 10, method `String.isBlank()` không tồn tại. Dùng `--release 10` để ngăn lỗi ngay trong build.

**Không khuyến khích compile cách thứ hai trong dự án mới.** Nó chỉ là negative/contrast lab để thấy `--source/-target` chưa đủ.

## 10. Test biên giới Java 10 và Java 11: lambda có `var`

Lưu **`LambdaVarDemo.java`**:

~~~java
import java.util.function.Function;

public final class LambdaVarDemo {

    public static void main(String[] args) {
        Function<String, Integer> length =
                (var s) -> s.length();

        System.out.println("length=" + length.apply("Java"));
    }
}
~~~

Với Java 10:

~~~bash
javac --release 10 LambdaVarDemo.java
~~~

**Kết quả mong đợi:** compile thất bại, vì cú pháp `var` ở tham số lambda được bổ sung ở **Java 11**, không phải Java 10.

Với Java 11:

~~~bash
mkdir out11
javac --release 11 -d out11 LambdaVarDemo.java
java -cp out11 LambdaVarDemo
~~~

**`stdout` đã kiểm thử trên JDK 24:**

~~~text
length=4
~~~

**Không suy “Java 11 có `var` trong lambda” thành “Java 10 cũng cho phép `var` ở mọi tham số”.** Java 10 cho phép suy luận kiểu **biến cục bộ**; hỗ trợ tham số lambda là một JEP khác, thuộc release khác.

## 11. Vì sao không dùng `--enable-preview` cho Java 10?

Một số tính năng Java hiện đại được phát hành ở trạng thái **preview** rồi sau đó có thể chính thức hóa. Tuy nhiên, **Local Variable Type Inference (`var`) trong Java 10 là tính năng chuẩn**; không cần preview flag.

Câu lệnh:

~~~bash
javac --release 10 --enable-preview SourceTenDemo.java
~~~

trên JDK 24.0.2 được kiểm thử **bị từ chối**. Với compiler đó, preview chỉ được hỗ trợ cho **current release 24**, không phải một target cũ như 10.

**Không dùng preview flags để “mở khóa tất cả tính năng ở những release cũ”.** Hãy biên dịch với đúng `--release` cần hỗ trợ và chỉ dùng preview cho current JDK khi có chủ đích, có quản lý rủi ro và cùng release trên runtime.

Khi học Java 10, chỉ cần `--release 10` để dùng những tính năng/ APIs đã chuẩn hóa ở release đó.

## 12. Bytecode compatibility khác API compatibility như thế nào?

Một class-file có phần header gồm **major/minor version**. JVM dùng phần này để biết nó có hỗ trợ định dạng class hay không.

| Java release | Class-file major |
| --- | --- |
| Java 8 | 52 |
| Java 9 | 53 |
| **Java 10** | **54** |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |
| Java 24 | 68 |
| Java 26 | 70 |

**Trên JVM cũ hơn:** một class file major 54 không thể tải bằng JVM Java 9 vốn chỉ hỗ trợ đến major 53. Lỗi thường gặp là `UnsupportedClassVersionError`.

**Trên JVM mới hơn:** JVM thường đọc được class file major 54, nhưng chương trình vẫn có thể thất bại bởi thư viện, native dependencies, internal APIs, security policy hoặc hành vi runtime khác.

**Nếu dùng `-source 10 -target 10` trên JDK mới:** compiler vẫn tạo major 54 nhưng **có thể đưa reference tới method Java 11**. Khi JVM Java 10 cố liên kết method không tồn tại, lỗi là **linkage error** dù class-file header được chấp nhận.

Vì thế cần ba lớp kiểm chứng:

1. Compiler report dùng **`--release 10`**.
2. `javap` xác nhận **major 54**.
3. Kiểm thử **trên runtime Java 10 thật** nếu đây là điều kiện tương thích bắt buộc, cùng dependencies và workload phù hợp.

## 13. Biên dịch bằng JDK mới có phải là dùng tính năng mới không?

**Không nhất thiết.** Có thể cài JDK 17, 21, 24 hoặc 26 để chạy build, nhưng vẫn yêu cầu language/API target 10.

Ví dụ:

~~~bash
javac --release 10 SourceTenDemo.java
~~~

Nếu compiler hỗ trợ release 10, nó sẽ kiểm tra theo Java 10, không vì đang chạy JDK 24 mà cho phép `String.isBlank()` hay cú pháp lambda `(var x) -> ...` từ Java 11.

Điều này rất hữu ích khi:

- Dự án thư viện vẫn cần phát hành artifact tương thích một runtime cũ.
- CI đang sử dụng JDK mới, có bảo trì/bản vá hiện hành.
- Cần ngăn dev vô tình dùng APIs mới hơn mức compatibility contract.

**Nhưng compiler JDK và runtime JDK vẫn là hai thành phần khác.** Sử dụng JDK 24 để biên dịch `--release 10` không tương đương với chạy unit/integration tests bằng JVM Java 10.

### Không cố chạy Java 10 trong production chỉ vì bài học

Java 10 là một release lịch sử không phải nhánh LTS hiện hành. Với ứng dụng mới nên chọn một **JDK được hỗ trợ và cập nhật bảo mật** làm runtime mục tiêu theo chính sách tổ chức.

Chỉ đặt `--release 10` khi yêu cầu tương thích Java 10 là thật, được quản trị và có kế hoạch thử nghiệm. Nếu sản phẩm yêu cầu Java 17 hoặc 21 trở lên, việc cố “ép xuống Java 10” có thể ngăn sử dụng API hiện đại cần thiết và tạo rủi ro hỗ trợ.

**Mục tiêu bài:** cách biên dịch đúng **khi cần** tương thích Java 10, không cổ vũ triển khai một runtime đã lỗi thời.

## 14. Các API bị chặn và giới hạn `--release`

`--release` giới hạn **Java platform APIs** theo phiên bản. Tài liệu Oracle Java SE 26 mô tả có những API trong Java SE và các JDK modules đã export tương ứng release đích; một số internal/undocumented packages không được cho phép chỉ vì compiler đang chạy trên JDK mới.

Ví dụ:

~~~java
// API Java 11:
"  ".isBlank();    // bị từ chối khi --release 10
~~~

### Cảnh báo về Java internals

Các packages nội bộ như `sun.*` hoặc các `jdk.internal.*` packages không phải public contract để tùy tiện import. Một số lệnh `--add-exports` có thể phá encapsulation khi compile theo current release, nhưng **`--release` của một release có module system không cho phép dùng `--add-exports` để mở rộng các packages được export bởi Java SE/JDK modules của release đích**.

**Không giải quyết lỗi compile target Java 10 bằng cách bỏ hết kiểm tra module boundaries hoặc thêm lệnh mở internal packages một cách không kiểm soát.** Nếu cần một public API, tìm lựa chọn được hỗ trợ trong Java 10 hoặc nâng declared minimum release.

### Một dependency không phải Java platform API

`--release 10` **không tự kiểm chứng toàn bộ các thư viện bên thứ ba** có class files và API tương thích Java 10. Nếu dependency build bằng Java 17, app có thể không load được nó trên JVM10 dù source chính đã compile bằng `--release 10`.

**Vì thế cần kiểm tra dependencies** (transitive dependencies, classifiers, shaded JARs), class-file major, compatibility matrix và runtime tests. Có thể dùng `jdeps` như công cụ bổ sung, nhưng nó không bao phủ mọi đường gọi qua reflection, service loading hoặc JNI.

## 15. Java Platform Module System khi target Java 10

Java 9 giới thiệu **Java Platform Module System (JPMS)**. Vì Java 10 có JPMS, một ứng dụng Java 10 có thể dùng `module-info.java`, module path và `requires` cho các modules phù hợp release.

Ví dụ **mô hình**:

~~~java
module example.demo {
    requires java.base;
}
~~~

Đây chỉ là **mảnh `module-info.java`**, không phải chương trình gồm các classes/package có thể chạy ngay. `java.base` được đọc ngầm bởi các modules, nên dòng `requires java.base` không bắt buộc; nó chỉ minh họa cú pháp JPMS.

### Các vấn đề khi compile modular app

- Module platform xuất hiện **sau Java 10** sẽ không sẵn có khi dùng `--release 10`.
- `--module-path` dùng cho những dependencies được công bố qua modules; `--class-path` dành cho dependencies kiểu classpath truyền thống.
- Một module cần truy cập internal JDK package không export sẽ bị kiểm tra theo module boundaries.
- Phải test cả **module graph**, packaging và startup command; có file major 54 chưa chứng minh module dependencies phù hợp.

**Không dùng các flags cũ của pre-module JDK** như bootclasspath tricks để ép platform APIs, vì Java 10 thuộc môi trường modules. Nếu dùng `--source/--target` vì lý do đặc biệt, tài liệu `javac` Java SE 26 hướng dẫn `--system` cho platform classes tương ứng JDK 9+; cách đơn giản hơn vẫn là `--release 10`.

## 16. Maven: khai báo đúng release mục tiêu

Trong dự án Maven dùng **Maven Compiler Plugin** hiện hành, cách rõ ràng nhất là đặt thuộc tính `maven.compiler.release`:

~~~xml
<project>
  <!-- Các phần project/model/dependencies khác theo dự án -->
  <properties>
    <maven.compiler.release>10</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>

  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.16.0</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

Đây là **đoạn cấu hình minh họa cấu trúc `pom.xml`**, không phải một POM độc lập đầy đủ để build nếu chưa có metadata cơ bản, dependencies và source files. Version plugin `3.16.0` là ví dụ theo tài liệu Maven Compiler Plugin được đối chiếu; khi dùng thực tế, chọn phiên bản plugin đáp ứng chính sách dự án và kiểm tra tài liệu hiện hành.

### Vì sao dùng `maven.compiler.release=10`?

Với `javac` hỗ trợ release 10, Maven Compiler Plugin truyền cấu hình tương ứng để:

- Chỉ cho phép cú pháp/source level Java 10.
- Sinh bytecode target 10.
- Dùng Java 10 platform API surface.

Nếu thay bằng:

~~~xml
<properties>
  <maven.compiler.source>10</maven.compiler.source>
  <maven.compiler.target>10</maven.compiler.target>
</properties>
~~~

thì chỉ đặt language/bytecode level, **không đủ để ngăn API leak từ JDK mới**. Tài liệu Maven khuyến nghị dùng `release` thay cho source/target khi khả dụng.

### Phân biệt Maven JVM và Java compiler/toolchain

- `mvn -version` cho biết JVM đang chạy Maven và thông tin môi trường.
- Compiler Plugin có thể dùng `javac` của JDK khác khi được cấu hình toolchain/fork.
- `maven.compiler.release=10` chỉ ràng buộc source/API/bytecode, **không tự thay đổi JVM Maven đang chạy** và không tự tạo runtime Java 10 để test.

**Không mặc định những thay đổi plugin sẽ xác minh các dependencies tương thích.** Sử dụng các bước dependency checks và integration tests phù hợp.

## 17. Gradle: toolchain và `options.release` phục vụ hai mục tiêu khác nhau

Gradle hiện hành đề xuất dùng **Java toolchain** để chọn compiler/runtime tools, và **`options.release`** để enforce một release API/language/bytecode cụ thể.

Ví dụ **`build.gradle.kts`**:

~~~kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(10)
    options.encoding = "UTF-8"
}
~~~

Ý nghĩa:

- Toolchain **JDK 17** dùng compiler từ JDK 17 (khi môi trường/Gradle cấu hình phù hợp).
- `options.release.set(10)` biên dịch source/API/bytecode theo Java 10, nếu `javac` đó hỗ trợ target 10.
- Gradle build/test tasks có thể dùng toolchain được cấu hình, nhưng **các test chạy bằng JDK 17 không thay thế test trên JVM Java 10**.

**Dùng đúng phiên bản Gradle hỗ trợ JDK chạy build và cú pháp Kotlin DSL của project.** Đoạn trên là cấu hình minh họa cho Gradle Java plugin, không phải một project đầy đủ tự chạy khi chưa có source files.

### Vì sao `sourceCompatibility/targetCompatibility` chưa đủ?

~~~groovy
sourceCompatibility = '10'
targetCompatibility = '10'
~~~

Đây là cách compatibility historically supported trong Gradle, nhưng tài liệu Gradle hiện hành nhấn mạnh nó **không chặn việc dùng JDK APIs mới hơn**. Trong project mới, `options.release = 10` (hoặc Kotlin DSL `options.release.set(10)`) được ưu tiên cho kiểm soát release.

**Không tự giả định toolchain Java 17 sẽ build được mọi dependency/plugin** của project. Toolchain kiểm soát compiler; compatibility của plugins, build JVM và thư viện vẫn phải được xác minh.

## 18. CI: quy trình build có thể tái lập

Một pipeline cần xác minh **target release**, **compiler JDK** và **runtime tests**:

~~~text
1. Pin JDK compiler version/build + build tool version
2. Resolve và pin/lock dependencies
3. Compile với --release 10
4. Run compile-negative tests cho feature/API >10 (nếu xây bài lab)
5. Inspect class major=54
6. Scan dependency bytecode/API compatibility
7. Run unit tests trên JDK đang build
8. Run integration/smoke tests trên runtime đích nếu yêu cầu
9. Package, lưu metadata build/manifest
10. Deploy với runtime được hỗ trợ và quan sát logs
~~~

Với **sản phẩm có compatibility contract Java 10**, việc chạy test trên một JVM Java 10 có thể cần môi trường cách ly và được tổ chức phê duyệt vì runtime cũ không có cập nhật bảo mật hiện hành. **Không dùng runtime cũ không được hỗ trợ trên môi trường production public chỉ để làm xong compatibility test**.

### Cần ghi lại những gì trong build report?

- `javac -version` của compiler.
- `javac --help` nếu phải xác minh target release.
- Command/Gradle/Maven effective `release`.
- `javap -verbose` cho class-file major.
- Dependency graph/version lock.
- JDK dùng để chạy test.
- Kết quả smoke/integration tests trên runtime đích.
- Artifact checksum, timestamp hoặc build metadata cần thiết cho reproducibility.

Không chỉ ghi “đã build trên JDK 24” rồi suy ra “ứng dụng yêu cầu Java 24”; một compiler JDK 24 hoàn toàn có thể **target Java 10**.

## 19. Khi nào `--release 10` vẫn chưa đủ bảo đảm tương thích?

### 19.1. Third-party libraries

Bạn có thể compile source chính theo Java 10 nhưng dependency `some-library.jar` được biên dịch với class major 61 (Java 17). Khi Java 10 load class đó, runtime có thể ném `UnsupportedClassVersionError`.

Kiểm tra cả **direct và transitive dependencies**. Không chỉ kiểm tra class chính.

### 19.2. Reflection và dynamic linking

Mã có thể gọi `Class.forName("...")`, dùng reflection để truy cập một class, hoặc tải plugin qua `ServiceLoader`. Những dependencies chỉ xuất hiện khi chạy có thể không được `javac --release` hoặc một static scan tìm thấy.

### 19.3. Native code/JNI

Bản binary native, DLL/SO, CPU architecture và OS version có thể khác. `--release 10` không khiến native dependencies tương thích với mọi runtime.

### 19.4. Security and truststore changes

TLS cipher suites, `cacerts`, provider policies và algorithm restrictions có thể thay đổi theo JDK. Bytecode target 10 không khóa được những hành vi runtime đó.

### 19.5. Multi-release JARs

JAR có thể chứa các class ở `META-INF/versions/...` với bytecode khác nhau. Kiểm tra main classes và **version-specific classes** nếu cần. Không kết luận chỉ từ một file đã được kiểm tra.

### 19.6. Annotation processing và code generation

Generated sources có thể chứa syntax hoặc API mới hơn Java 10. Hãy compile generated output bằng cùng release constraints, và nhớ annotation processor tự nó có thể cần một JVM compiler mới để chạy.

### 19.7. Module graph và ServiceLoader

Một runtime đích có thể thiếu modules/dependencies phù hợp hoặc có cấu trúc đóng gói khác. Kiểm tra module graph và startup thực tế, không chỉ build.

**Quy tắc:** `--release 10` là **rào chắn rất mạnh cho Java platform compatibility**, nhưng **không phải bằng chứng hoàn chỉnh rằng toàn bộ artifact và deployment chạy được trên mọi JVM Java 10**.

## 20. Lỗi compile hay gặp và cách xử lý

| Hiện tượng | Khả năng nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| `var` không nhận ra khi `--release 9` | Java 9 chưa có local-variable inference | Nếu yêu cầu Java 10, dùng `--release 10` |
| `cannot find symbol: isBlank()` với `--release 10` | `String.isBlank` từ Java 11 | Dùng API Java 10 phù hợp hoặc nâng minimum release |
| Lambda `(var x) -> ...` bị từ chối ở release 10 | `var` cho lambda parameters từ Java 11 | Dùng `x -> ...` hoặc nâng target nếu được phép |
| `--release` cùng `--source`/`--target` bị lỗi | Tùy chọn xung đột | Giữ một `--release 10` |
| `--enable-preview` cùng `--release 10` bị từ chối trên JDK mới | Preview chỉ dành current release của compiler | Không dùng preview cho Java 10 |
| `javap` cho major 68 thay vì 54 | Compile theo JDK 24 mặc định hoặc sai cấu hình | Xác minh effective `--release 10` và output directory |
| Runtime Java 9 báo `UnsupportedClassVersionError` | Class major 54 không được JVM9 đọc | Chạy trên JVM10+ theo yêu cầu, hoặc compile mã tương thích 9 |
| Runtime Java 10 báo `NoSuchMethodError` | API mới lọt vào qua source/target hoặc dependency | Biên dịch với `--release 10`, kiểm tra dependencies |
| `java -cp out10 ...` báo `ClassNotFoundException` | Sai classpath, package name hoặc output directory | Kiểm tra `-d`, package và `-cp` |
| Compiler báo release 10 không được hỗ trợ | Target đã không còn trong bộ release của compiler/JDK chọn | Dùng toolchain có hỗ trợ, xem `javac --help` |
| IDE compile được nhưng CI thất bại | IDE và CI dùng JDK/release khác nhau | Pin project SDK, compiler release và build tool config |
| CI thành công nhưng production fail | Runtime/dependencies không được kiểm tra | Smoke test trên target + dependency scan |

**Không sửa lỗi “API không tồn tại ở Java 10” bằng cách bỏ `--release 10`.** Cách đó chỉ giấu lỗi compile và đẩy rủi ro ra runtime.

## 21. Phân biệt compiler error, class loading error và API linkage error

### Compiler error

Ví dụ `String.isBlank()` dưới `--release 10`:

~~~text
Compilation failed
cannot find symbol: method isBlank()
~~~

Đây là **mẫu mô tả bản chất lỗi**, không phải bản chép chính xác mọi ký tự compiler in ra. Cần kiểm tra exit code và diagnostic của JDK đang chạy.

### Class format loading error

Nếu JVM không hỗ trợ major version của `.class`:

~~~text
java.lang.UnsupportedClassVersionError
~~~

Đây là lỗi tương thích **định dạng bytecode**, có thể xảy ra trước khi một phương thức được gọi.

### Method linkage error

Nếu class-format phù hợp nhưng bytecode gọi một method **không có trên runtime**:

~~~text
java.lang.NoSuchMethodError
~~~

Có thể xảy ra khi code được compile bằng source/target cũ nhưng API mới lọt vào. Lỗi có thể xuất hiện **khi code path thực thi và method được liên kết**, không nhất thiết ngay lúc JVM bắt đầu tải class.

### Nhìn nhận đúng các lỗi

- `UnsupportedClassVersionError`: lớp biên dịch cho phiên bản JVM quá mới.
- `NoSuchMethodError`: tại runtime thiếu phương thức mong đợi.
- `NoClassDefFoundError`: một class mà bytecode cần không có/không khởi tạo được trong điều kiện thích hợp.
- `ClassNotFoundException`: đường tìm kiếm class (qua API load) không tìm thấy tên yêu cầu.

**Không dùng một tên lỗi để suy toàn bộ nguyên nhân.** Cần kiểm tra JVM version, classpath/module path, dependencies và source/release config.

## 22. Một quy trình xác minh hoàn chỉnh trên máy của bạn

Trên hệ thống đã cài JDK mới có hỗ trợ release 10:

**Bước 1 — xác nhận công cụ:**

~~~bash
javac -version
java -version
javac --help
~~~

**Bước 2 — tạo `SourceTenDemo.java` như mục 7, rồi biên dịch:**

~~~bash
mkdir out10
javac --release 10 -encoding UTF-8 -d out10 SourceTenDemo.java
~~~

**Bước 3 — chạy bằng JVM hiện có:**

~~~bash
java -cp out10 SourceTenDemo
~~~

**Bước 4 — kiểm tra bytecode:**

~~~bash
javap -verbose -classpath out10 SourceTenDemo
~~~

Tìm `major version: 54`.

**Bước 5 — negative test syntax/API:**

~~~bash
javac --release 9 SourceTenDemo.java
javac --release 10 ApiElevenDemo.java
javac --release 10 LambdaVarDemo.java
~~~

Ba lệnh trên **được thiết kế để trả lỗi**. Đừng coi chúng là bước “cần sửa để build thành công”; đây là kiểm thử các ranh giới Java 9/10/11.

**Bước 6 — kiểm tra build tool:** Maven dùng `maven.compiler.release=10`, Gradle dùng `options.release.set(10)`.

**Bước 7 — runtime compatibility:** kiểm tra dependencies và chạy kiểm thử trên runtime đích phù hợp; đây là bước thêm ngoài `javac`.

### Tách output directory của các phiên bản

Nếu bạn đang compile cùng tên class bằng nhiều release, hãy dùng:

~~~text
out9/
out10/
out11/
~~~

Tránh để class files cũ ở cùng thư mục rồi vô tình chạy sai artifact. Với Maven/Gradle, quy trình `clean`, source sets và test tasks phải đảm bảo output không chứa lớp từ build config khác.

**Không cần xóa toàn bộ repository** để kiểm tra class-file version; chỉ làm sạch đúng build output được quản lý.

## 23. Bài tập tự kiểm tra

### Câu 1 — công cụ đúng

**Hỏi:** Trên JDK 24 muốn compile mã dùng `var` và giới hạn API theo Java 10 nên dùng flag nào?

**Đáp án:** `javac --release 10` nếu compiler hỗ trợ. Nó kiểm tra cú pháp, target class file và platform APIs của Java 10.

### Câu 2 — `--source` có đủ không?

**Hỏi:** `javac --source 10 --target 10` tạo class major 54; có chắc không gọi API Java 11?

**Đáp án:** Không. Hai flag này không ràng buộc platform API theo release 10; cần `--release 10` hoặc phương án platform libraries chính xác.

### Câu 3 — kiểu của `var`

**Hỏi:** `var total = 5;` có thể đổi kiểu thành `String` ở assignment sau không?

**Đáp án:** Không. Compiler đã suy ra kiểu tĩnh `int` cho biến tại declaration, không có dynamic typing.

### Câu 4 — lambda

**Hỏi:** Vì sao `(var value) -> value.length()` không hợp lệ khi `--release 10`?

**Đáp án:** `var` trong lambda parameter là **Java 11**, theo JEP 323.

### Câu 5 — Java 10 API

**Hỏi:** `List.copyOf` và `Optional.orElseThrow()` không tham số có được dùng khi `--release 10` không?

**Đáp án:** Có; chúng được đưa vào Java 10.

### Câu 6 — Java 11 API

**Hỏi:** `String.isBlank()` có được dùng khi target Java 10 không?

**Đáp án:** Không. API này có từ Java 11, `--release 10` sẽ ngăn từ compile.

### Câu 7 — bytecode

**Hỏi:** Class file major version nào tương ứng Java 10?

**Đáp án:** **54**.

### Câu 8 — runtime Java 9

**Hỏi:** Một class file major 54 có chạy trên JVM 9 không?

**Đáp án:** Không; JVM 9 chỉ hỗ trợ tối đa class major 53.

### Câu 9 — flag conflict

**Hỏi:** Có nên đặt `--release 10 --source 10 --target 10` để “chắc chắn” không?

**Đáp án:** Không. `--release` xung đột với `--source/--target`, chỉ cần `--release 10`.

### Câu 10 — build tool

**Hỏi:** Maven/Gradle nên dùng cấu hình nào để chặn API Java mới khi target 10?

**Đáp án:** Maven `maven.compiler.release=10`; Gradle `options.release.set(10)` với toolchain phù hợp.

### Câu 11 — dependency mới

**Hỏi:** Source chính compile `--release 10` nhưng dependency dùng major 61. Có an toàn trên JVM10 không?

**Đáp án:** Không. JVM10 không đọc được dependency class major 61, cần dependency tương thích hoặc thay minimum runtime.

### Câu 12 — runtime testing

**Hỏi:** Biên dịch `--release 10` bằng JDK24 và chạy thành công trên JDK24 đã chứng minh chạy được JVM10 thật chưa?

**Đáp án:** Chưa. Compiler đã kiểm tra Java platform API/language/bytecode, nhưng vẫn cần runtime tests và dependency checks nếu Java10 compatibility là cam kết.

### Câu 13 — preview

**Hỏi:** Muốn dùng `var` của Java10 có cần `--enable-preview` không?

**Đáp án:** Không; local-variable type inference là tính năng chuẩn từ Java10.

### Câu 14 — class-major-only

**Hỏi:** Vì sao `javap major version: 54` không đủ chứng minh ứng dụng thực sự tương thích Java10?

**Đáp án:** Method references tới API Java11 hoặc dependency mới vẫn có thể xuất hiện dù file có major54 nếu compile không khóa API bằng `--release`.

### Câu 15 — CI

**Hỏi:** CI build qua JDK21, local qua JDK17, đều khai báo `--release 10`. Có cần lưu JDK version thực tế không?

**Đáp án:** Có. Pin toolchain/build, kiểm tra các target supported và dependency/tool behavior để pipeline tái lập và kết quả kiểm thử rõ ràng.

## 24. Checklist trước khi phát hành artifact nhắm Java 10

- [ ] Đã xác nhận **compatibility requirement Java 10** là nhu cầu thật, không chỉ copy một cấu hình cũ.
- [ ] Sử dụng compiler JDK có hỗ trợ `--release 10`.
- [ ] Có `--release 10` trong `javac` hoặc effective Maven/Gradle build config.
- [ ] Không trộn `--release` với `--source` hoặc `--target`.
- [ ] Đã dùng `var` đúng những vị trí Java 10 cho phép.
- [ ] Không vô tình dùng `var` cho lambda parameters (Java 11) hoặc APIs mới hơn.
- [ ] Đã xác nhận `List.copyOf` và `Optional.orElseThrow()` được dùng đúng API Java10.
- [ ] Build không chứa `String.isBlank()` hoặc class/module Java11+ ngoài compat contract.
- [ ] Kiểm tra `javap` thấy class major **54**.
- [ ] Kiểm tra **toàn bộ dependencies** (bao gồm transitive, generated code, shaded JARs).
- [ ] Kiểm tra module graph/classpath và JPMS constraints khi dùng modules.
- [ ] Dùng source encoding thống nhất, ví dụ UTF-8.
- [ ] Không để class files cũ lẫn vào output sau khi đổi release.
- [ ] CI ghi lại compiler version, build tool version và effective release.
- [ ] Unit tests chạy với build artifact thật.
- [ ] Runtime/integration tests trên target JDK nếu đây là yêu cầu tương thích chặt.
- [ ] Không phụ thuộc vào JDK internals hoặc API bị cấm của release đích.
- [ ] Không đánh đồng thành công compile với thành công ở runtime và production.
- [ ] Nếu triển khai mới, cân nhắc một **JDK được hỗ trợ hiện hành** thay cho Java10 runtime cũ.

## 25. Tổng kết và tài liệu chính thức

**Để biên dịch các tính năng Java 10 đúng với ranh giới source/API/bytecode của Java 10, hãy ưu tiên `javac --release 10` trên compiler có hỗ trợ release 10.** `var` của Java 10 (JEP 286), `List.copyOf` và `Optional.orElseThrow()` không tham số được chấp nhận. Cú pháp `(var x) -> ...` trong lambda và `String.isBlank()` thuộc Java 11 nên bị chặn khi target Java 10.

**`--release 10` sinh class-file major 54**, nhưng vẫn phải xét third-party dependencies và runtime tests. `--source 10 --target 10` không đủ bảo đảm API tương thích. Trong Maven/Gradle hiện đại, hãy dùng các thuộc tính **release** thay vì chỉ đặt source/target.

### Nguồn chính thức còn phù hợp

1. [Oracle Java SE 26 — `javac` command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html): `--release`, `--source`, `--target`, support các release cũ và giới hạn Java platform API.
2. [OpenJDK — JEP 286: Local-Variable Type Inference](https://openjdk.org/jeps/286): `var` cho local declarations từ Java 10.
3. [OpenJDK — JEP 323: Local-Variable Syntax for Lambda Parameters](https://openjdk.org/jeps/323): bổ sung `var` ở lambda parameters từ Java 11.
4. [Oracle Java SE 17 — Local Variable Type Inference](https://docs.oracle.com/en/java/javase/17/language/local-variable-type-inference.html): kiểu tĩnh suy luận và phạm vi `var`.
5. [Oracle Java SE 26 — JVMS, Java 10 class major 54](https://docs.oracle.com/en/java/javase/26/docs/specs/jvms/jvms-1.html): mapping release/class-file versions.
6. [Oracle Java SE 26 — `List.copyOf` API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)): "Since: 10".
7. [Oracle Java SE 26 — `Optional.orElseThrow()` API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Optional.html#orElseThrow()): "Since: 10".
8. [Oracle Java SE 26 — `String.isBlank()` API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/String.html#isBlank()): "Since: 11".
9. [Apache Maven Compiler Plugin — Set Compiler Release](https://maven.apache.org/plugins/maven-compiler-plugin/examples/set-compiler-release.html): `maven.compiler.release` và lý do ưu tiên release.
10. [Apache Maven — Guide to Targeting a Java Version](https://maven.apache.org/guides/mini/guide-java-target.html): source/target vs release và compatibility.
11. [Gradle — Toolchains for JVM Projects](https://docs.gradle.org/current/userguide/toolchains.html): tách compiler toolchain và `options.release`.
12. [Gradle — Building Java Projects](https://docs.gradle.org/current/userguide/building_java_projects.html): sourceCompatibility/targetCompatibility không khóa JDK APIs cũ.
