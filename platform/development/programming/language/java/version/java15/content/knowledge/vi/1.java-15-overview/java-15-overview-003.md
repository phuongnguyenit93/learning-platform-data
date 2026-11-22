# Phân biệt tính năng ngôn ngữ, API chuẩn và cơ chế của JVM

> **Phạm vi:** Java 15 và kiến thức vẫn áp dụng trên các JDK hiện đại. Bài học tập trung vào những đặc tính đã được chuẩn hóa và các cơ chế còn được sử dụng; ví dụ không cần bật tính năng preview hay gọi API nội bộ.

## 1. Vì sao cần phân biệt ba lớp?

Khi nói “Java hỗ trợ tính năng X”, cần xác định **X thuộc lớp nào**. Một cú pháp mới, một phương thức thư viện mới và một cải tiến của máy ảo có vòng đời, cách sử dụng và mức độ tương thích khác nhau. Nhầm lẫn ba lớp dễ dẫn đến các kết luận sai như “thêm một phương thức vào `String` tức là đổi cú pháp Java” hoặc “đổi garbage collector sẽ thay đổi ý nghĩa của chương trình”.

| Lớp | Câu hỏi nhận diện | Hợp đồng chính | Ví dụ |
| --- | --- | --- | --- |
| **Ngôn ngữ Java** | Lập trình viên được *viết* cấu trúc mã nguồn nào, cấu trúc đó có nghĩa gì? | **Java Language Specification (JLS)** | `class`, `interface`, lambda `->`, biểu thức `switch`, text block `"""..."""` |
| **API chuẩn Java SE** | Chương trình được *gọi* lớp, interface, phương thức hay dịch vụ nào? | **Java SE API Specification** và hợp đồng của từng API | `List.of`, `String.lines`, `Files.readString`, `HttpClient`, `Signature` |
| **JVM / cơ chế thực thi** | Mã đã biên dịch được *nạp, kiểm tra, liên kết và chạy* như thế nào? | **Java Virtual Machine Specification (JVMS)**; chi tiết triển khai phụ thuộc JVM | Bytecode, class loading, bytecode verification, heap/stack, thực thi, garbage collection |

Sơ đồ liên hệ:

~~~text
Mã nguồn .java
    |  cú pháp, kiểu và ngữ nghĩa: JLS
    v
javac (công cụ trong JDK)
    |
    v
File .class / bytecode
    |  định dạng class, lệnh VM, nạp và kiểm tra: JVMS
    v
JVM thực thi chương trình
    |\
    | \-- JIT, bộ thu gom rác, chiến lược tối ưu: chi tiết triển khai JVM
    |
    +---- Chương trình gọi thư viện Java SE (API)
               |
               +-- Thư viện có thể tương tác với JVM và hệ điều hành
~~~

**Một dòng mã có thể đi qua cả ba lớp**, nhưng mỗi lớp trả lời một câu hỏi khác nhau. JDK là bộ công cụ và thư viện để phát triển/chạy Java, còn JVM là môi trường thực thi bytecode; `javac` là trình biên dịch của JDK, không phải một thành phần bắt buộc bên trong JVM.

## 2. Lớp ngôn ngữ: cú pháp và ngữ nghĩa của mã nguồn

Một tính năng ngôn ngữ ảnh hưởng đến cách parser/compiler hiểu chương trình, quy tắc kiểu, phạm vi biến, biểu thức hoặc cấu trúc điều khiển. Để xác nhận, đọc **JLS**, không chỉ tìm một lớp có tên gần giống trong tài liệu API.

Ví dụ:

- `if`, `for`, `try/catch`, `new`, generic type arguments và lambda là các cấu trúc/cơ chế được định nghĩa ở cấp ngôn ngữ.
- `"a" + "b"` dùng toán tử cộng chuỗi theo ngữ nghĩa Java; compiler/JVM có thể chọn các cách triển khai khác nhau miễn giữ kết quả được đặc tả.
- **Text block** là cách viết literal chuỗi nhiều dòng, được chuẩn hóa từ Java 15 (JEP 378). Nó tạo ra một `String` thông thường; đây là **cú pháp ngôn ngữ**, không phải một lớp “TextBlock” trong thư viện.

Ví dụ về text block:

~~~java
String message = """
        Xin chào
        Java
        """;
System.out.print(message);
~~~

Đây là **đoạn minh họa đặt bên trong một phương thức**, không phải chương trình độc lập. Nội dung chuỗi có hai dòng và ký tự xuống dòng ở cuối, nên khi in sẽ được:

~~~text
Xin chào
Java
~~~

Dấu `"""` mở/đóng, quy tắc loại bỏ thụt đầu dòng phụ và cách xử lý newline là quy tắc của *ngôn ngữ*. Còn các lời gọi như `message.strip()`, `message.lines()` là *API* của `java.lang.String`. Khi text block là dữ liệu JSON/SQL, hãy kiểm tra newline, khoảng trắng và cơ chế escape thay vì cho rằng nó giữ nguyên từng dấu cách trong source.

Một số tính năng hiện **ổn định** nhưng cần ghi đúng mốc phiên bản: pattern matching cho `instanceof` chính thức từ Java 16; `record` chính thức từ Java 16; `sealed` class/interface chính thức từ Java 17. Chúng từng xuất hiện ở trạng thái preview quanh Java 15, vì vậy **không được gọi chúng là tính năng hoàn thiện của Java 15**. Với dự án mới trên JDK đủ mới, dùng cú pháp đã hoàn thiện và không cần `--enable-preview`.

## 3. Lớp API chuẩn: những khả năng chương trình có thể gọi

API gồm các **kiểu, hàm, hằng và hợp đồng hành vi** công khai. Một API có thể được mở rộng mà không sửa ngữ pháp Java; chương trình chỉ cần biên dịch với phiên bản thư viện phù hợp.

Các ví dụ còn dùng rộng rãi:

| API | Hợp đồng dành cho ứng dụng | Lưu ý phân lớp |
| --- | --- | --- |
| `java.util.List` / `List.of` | Tạo và thao tác danh sách; danh sách từ `List.of` không hỗ trợ thao tác thay đổi phần tử/cấu trúc | API tập hợp; cú pháp khai báo biến/generic là ngôn ngữ |
| `java.lang.String.lines` | Tạo luồng các dòng từ chuỗi | API xử lý chuỗi; bản thân text block là cú pháp |
| `java.nio.file.Files.readString` | Đọc nội dung tệp thành chuỗi, có thể phát sinh lỗi I/O | API thao tác tệp; việc truy cập tệp liên quan hệ điều hành |
| `java.net.http.HttpClient` | Gửi HTTP request/nhận response theo hợp đồng API | API mạng; socket/TLS và lịch chạy là công việc của thư viện/runtime/hệ điều hành |
| `java.security.Signature` | Tạo hoặc kiểm tra chữ ký số thông qua tên thuật toán và security provider | API bảo mật; thuật toán/provider thực thi việc ký |

Trong bối cảnh Java 15, **EdDSA (JEP 339)** là một ví dụ quan trọng về **bổ sung khả năng bảo mật thông qua API/provider chuẩn**, không phải cú pháp ngôn ngữ. Chẳng hạn:

~~~java
java.security.Signature verifier =
        java.security.Signature.getInstance("Ed25519");
~~~

Đây là **đoạn minh họa bên trong phương thức**; việc dùng thuật toán còn phụ thuộc security provider có hỗ trợ. `getInstance` là API public; `Ed25519` là tên thuật toán; quá trình tính toán chữ ký do provider thực hiện. Không suy ra rằng Java có từ khóa `Ed25519` hoặc JVM có một lệnh bytecode riêng dành cho thuật toán này.

**Cách nhận diện API “chuẩn”:** tra đặc tả và module tương ứng. Nhiều API Java SE ở các module `java.*` và package `java.*`; cũng có API chuẩn với package `javax.*`, chẳng hạn `javax.crypto`. Ngược lại, package `jdk.*` thường là API/công cụ riêng của JDK, không tự động trở thành hợp đồng chung của mọi triển khai Java SE; `sun.*` và các gói nội bộ càng không nên được coi là API ứng dụng ổn định. Thư viện bên thứ ba như Spring không biến thành Java SE API dù được dùng phổ biến.

## 4. Lớp JVM: thực thi bytecode và quản lý tài nguyên

JVM nhận các class file hợp lệ theo đặc tả và thực thi những chỉ dẫn cùng quy tắc runtime. Các phần quan trọng:

1. **Nạp lớp (loading):** bộ nạp lớp đưa định nghĩa class vào môi trường runtime. Tên class, class loader và module có thể ảnh hưởng khả năng tìm thấy lớp.
2. **Liên kết (linking):** gồm kiểm tra bytecode (verification), chuẩn bị (preparation) và có thể phân giải tham chiếu ký hiệu (resolution) vào thời điểm phù hợp. Không nên coi toàn bộ liên kết luôn hoàn tất ngay khi vừa load class.
3. **Khởi tạo (initialization):** chạy logic khởi tạo class theo quy tắc JLS/JVMS khi class được sử dụng lần đầu theo các điều kiện đặc tả.
4. **Thực thi:** JVM thực hiện bytecode, quản lý frame/operand stack và các vùng dữ liệu runtime. JVM cụ thể có thể thông dịch hoặc biên dịch máy bằng **JIT**; ứng dụng không được dựa vào việc có JIT hay một ngưỡng tối ưu cố định.
5. **Quản lý bộ nhớ:** JVM quản lý cấp phát/thu hồi bộ nhớ heap và garbage collection. Các collector như G1, ZGC, Shenandoah là lựa chọn **triển khai/runtime**, có thể khác nhau giữa nhà cung cấp, phiên bản và cấu hình; chúng không làm thay đổi ý nghĩa của `new` trong ngôn ngữ.

Một số quy tắc dễ nhầm:

- `new ArrayList<>()`: `new` và cú pháp diamond `<>` là **ngôn ngữ**; `ArrayList` là **API**; cấp phát object, tracking heap và GC thuộc **runtime**.
- `Thread.start()` là **API**; việc thread nào được chạy trước là kết quả của JVM và bộ lập lịch hệ điều hành, trừ các bảo đảm cụ thể của Java Memory Model/happens-before. Đừng dựa vào thứ tự in giữa hai thread không được đồng bộ.
- `System.gc()` là **API** đưa ra yêu cầu/gợi ý cho runtime; không bảo đảm garbage collection sẽ diễn ra ngay hay một lượng bộ nhớ cụ thể sẽ được thu hồi.
- `Class.forName(...)` và reflection là **API** tương tác với quá trình nạp class, kiểm tra kiểu và runtime; vì liên quan JVM nên chúng không tự trở thành “cú pháp Java”.
- **Hidden classes** (JEP 371, có trong Java 15) phục vụ nhu cầu tạo class runtime của framework/công cụ. Đây là năng lực runtime được tiếp cận thông qua API công khai thích hợp như `MethodHandles.Lookup`, không phải từ khóa mới cho lập trình ứng dụng thông thường.

**Chú ý:** JVMS đặc tả các nghĩa vụ của JVM, nhưng không bắt buộc mọi máy ảo sử dụng cùng bộ thu gom rác, cùng JIT, cùng chiến lược phân bổ heap hay có cùng tùy chọn dòng lệnh `-XX`. Cần phân biệt **hành vi được Java bảo đảm** với **chi tiết của một bản JVM cụ thể**.

## 5. Một chương trình đi qua đủ ba lớp

Lưu toàn bộ chương trình sau trong tệp **`LayersDemo.java`**:

~~~java
import java.util.List;
import java.util.stream.Collectors;

public class LayersDemo {
    public static void main(String[] args) {
        String input = """
                java
                api
                jvm
                """;

        List<String> upper = input.lines()
                .map(String::toUpperCase)
                .collect(Collectors.toList());

        System.out.println(upper);
    }
}
~~~

Chạy trên JDK 17+ (các API và cú pháp được dùng trong ví dụ cũng có sẵn từ Java 15):

~~~bash
javac LayersDemo.java
java LayersDemo
~~~

**Stdout chính xác:**

~~~text
[JAVA, API, JVM]
~~~

Đọc mã theo từng lớp:

| Biểu thức/thành phần | Phân loại chính | Giải thích |
| --- | --- | --- |
| `public class`, `static`, khai báo biến và generic `List<String>` | Ngôn ngữ | Cú pháp/kiểu được compiler kiểm tra |
| `"""..."""` | Ngôn ngữ | Text block đã chính thức trong Java 15 |
| `input.lines()` | API chuẩn | Phương thức `String.lines` |
| `.map(...)`, `.collect(...)`, `Collectors.toList()` | API chuẩn | Phương thức Stream/Collector |
| `String::toUpperCase` | **Cả hai:** `::` là cú pháp tham chiếu phương thức; `toUpperCase` là API | Một biểu thức phối hợp cú pháp với phương thức thư viện |
| `System.out.println(upper)` | API chuẩn | API xuất dữ liệu; I/O được thư viện/runtime hiện thực |
| Bytecode được sinh, xác minh, chạy, đối tượng được cấp phát | JVM/runtime | Cách thực thi mã đã biên dịch |

Kiểm tra mã bytecode bằng công cụ JDK:

~~~bash
javap -c LayersDemo
~~~

`javap` cho thấy các bytecode của phương thức. Cấu trúc hiển thị và cách compiler mã hóa một số biểu thức có thể khác theo bản JDK; **bytecode là mức trung gian**, không đồng nghĩa toàn bộ máy ảo sẽ chỉ thông dịch từng lệnh mà không tối ưu.

Để xác minh API nào sẵn có trong một phiên bản Java mục tiêu khi đang dùng JDK mới, có thể biên dịch bằng `javac --release N` với `N` là phiên bản mà compiler hỗ trợ. Tùy chọn này ràng buộc mức ngôn ngữ, định dạng class file và API chuẩn được công cụ biết cho bản đích; nó **không mô phỏng toàn bộ JVM hay hành vi của hệ điều hành**. Ví dụ kiểm tra rằng chương trình trên không dùng API mới hơn Java 15:

~~~bash
javac --release 15 LayersDemo.java
~~~

Đây là **kiểm tra tương thích nguồn/API**; khi triển khai thực tế vẫn cần chạy thử trên runtime mục tiêu được hỗ trợ và cập nhật bảo mật.

## 6. Đọc đúng các thay đổi được nhắc đến quanh Java 15

Khi gặp một bài viết về “Java 15 features”, trước tiên xác định thay đổi thuộc JLS, thư viện hay JVM; tiếp theo xác định liệu nó đã **final** trong bản đó hay mới ở trạng thái **preview**. Những ví dụ dưới đây vẫn có ý nghĩa trong Java hiện đại:

| Nội dung | Lớp chính | Mốc chính thức / cách hiểu đúng |
| --- | --- | --- |
| **Text Blocks (JEP 378)** | Ngôn ngữ | Hoàn thiện trong **Java 15**; cú pháp nhiều dòng vẫn dùng bình thường |
| **EdDSA (JEP 339)** | API + security provider | Được bổ sung trong **JDK 15**; lập trình viên dùng API crypto, provider cung cấp triển khai |
| **Hidden Classes (JEP 371)** | Runtime/JVM + API hỗ trợ | Có từ **Java 15**; phù hợp công cụ/framework sinh class động |
| **Pattern matching cho `instanceof`** | Ngôn ngữ | Là preview trong Java 15, **hoàn thiện từ Java 16** |
| **Records** | Ngôn ngữ (có hỗ trợ ở class file/runtime) | Là preview trong Java 15, **hoàn thiện từ Java 16** |
| **Sealed Classes/Interfaces** | Ngôn ngữ (có quy tắc kiểm tra ở runtime) | Là preview trong Java 15, **hoàn thiện từ Java 17** |
| **Lựa chọn garbage collector** | JVM triển khai | G1/ZGC/Shenandoah là cơ chế runtime; tính sẵn có và cấu hình phụ thuộc JDK đang chạy |

Vì bài học ưu tiên kiến thức còn áp dụng hiện nay, **không sử dụng cú pháp preview cũ, công cụ đã ngừng hỗ trợ hay API nội bộ như một hướng dẫn thực hành**. Các mốc preview chỉ xuất hiện để tránh gọi nhầm thứ tự “giới thiệu” và “chuẩn hóa”.

## 7. Cách tự phân loại một tính năng mới

Áp dụng chuỗi câu hỏi này mỗi khi đọc release notes, tài liệu hoặc một dòng mã khó hiểu:

1. **Có cú pháp/từ khóa/quy tắc kiểu mới không?** Kiểm tra JLS, mục “language feature” và trạng thái final/preview.
2. **Có lớp, interface, phương thức, module hoặc hợp đồng công khai mới không?** Kiểm tra Java SE API Specification và trường `Since` trên Javadoc. Đừng đoán chỉ từ tên package.
3. **Có thay đổi class file, bytecode, class loading, memory model, runtime data area không?** Kiểm tra JVMS hoặc JEP về VM.
4. **Có nhắc GC, JIT, tùy chọn `-XX`, tối ưu hiệu năng hoặc provider riêng không?** Xác định đó là chi tiết một bản triển khai; tra tài liệu nhà cung cấp, không khái quát thành bảo đảm chung của Java.
5. **Thay đổi có tác động đồng thời nhiều lớp không?** Nêu từng lớp cụ thể. Ví dụ `record` là cú pháp ngôn ngữ nhưng có metadata class file và runtime support; API reflection có thể đọc thông tin record.
6. **Phiên bản nào hỗ trợ?** Phân biệt thời điểm JEP được đề xuất/preview, phiên bản hoàn thiện, mức `--release` của compiler và runtime mà ứng dụng thực sự chạy.

Ba loại tài liệu chính thức có vai trò khác nhau: **JLS** trả lời “mã Java hợp lệ và có nghĩa gì?”, **Java SE API Specification** trả lời “được phép gọi gì và hợp đồng ra sao?”, còn **JVMS** trả lời “class file và VM phải thực thi như thế nào?”. Release notes/JEP giải thích vì sao và khi nào một thay đổi xuất hiện, nhưng không thay cho đặc tả cuối cùng.

## 8. Lỗi phổ biến và cách sửa

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “Có `String.lines()` nên Java có cú pháp `lines`.” | `lines` là phương thức **API**; `.` và cú pháp gọi phương thức thuộc **ngôn ngữ**. |
| “Text block là API Java 15.” | Text block là **cú pháp literal** Java 15; giá trị được tạo là đối tượng `String`. |
| “JDK 15 có record nên record đã final trong Java 15.” | Record khi đó ở trạng thái **preview**; cú pháp chính thức từ **Java 16**. |
| “`new`/GC là cùng một tính năng.” | `new` có ngữ nghĩa trong JLS; GC là chiến lược quản lý bộ nhớ của runtime. |
| “Java API bảo đảm thứ tự các thread.” | Chỉ những quy tắc đồng bộ và Java Memory Model mới tạo bảo đảm liên quan; lịch chạy thực tế có thể khác nhau. |
| “Chạy tốt trên HotSpot nghĩa là mọi JVM phải có cùng cờ `-XX`.” | Các cờ `-XX` thường là **tùy chọn của triển khai**, không phải hợp đồng Java SE. |
| “Compiler và JIT là một.” | `javac` tạo bytecode từ mã nguồn; **JIT** là một chiến lược của JVM để tối ưu mã khi chạy. |
| “Mọi package `jdk.*` đều là API Java SE chuẩn.” | Phải kiểm tra module và đặc tả; API của JDK có thể chỉ được bảo đảm trong sản phẩm JDK cụ thể. |

## 9. Bài tập tự kiểm tra

**Bài 1.** Phân loại các mảnh sau và giải thích một câu cho mỗi mảnh:

~~~java
String text = """
        one
        two
        """;
long count = text.lines().count();
System.out.println(count);
~~~

**Đáp án:** text block và cú pháp khai báo là **ngôn ngữ**; `String.lines`, `Stream.count`, `System.out.println` là **API**; việc bytecode thực thi và thu hồi các đối tượng trung gian là **runtime**. Vì chuỗi chứa hai dòng có nội dung, giá trị in là **`2`**.

**Bài 2.** “Thay GC của một ứng dụng từ collector A sang collector B đồng nghĩa với cập nhật ngôn ngữ Java”. Đúng hay sai? **Sai.** Đây là thay đổi cấu hình/cơ chế của bản JVM cụ thể; vẫn cần benchmark, kiểm tra độ trễ, throughput, RAM và khả năng hỗ trợ của runtime, nhưng không viết lại cú pháp Java chỉ vì đổi collector.

**Bài 3.** “Lời gọi `Signature.getInstance("Ed25519")` là tính năng ngôn ngữ mới của Java 15”. Đúng hay sai? **Sai.** Đây là API bảo mật sử dụng một tên thuật toán; JDK/provider cung cấp khả năng EdDSA, còn cú pháp gọi phương thức của Java không thay đổi.

**Bài 4.** Khi một tính năng vừa thêm cú pháp mới vừa thay đổi metadata class file, chỉ được chọn một nhãn hay không? **Không.** Xác định **lớp chủ đạo và những lớp liên quan**; trường hợp record là một ví dụ.

## 10. Tài liệu tham khảo chính thức

- **Java Language Specification và Java Virtual Machine Specification:** https://docs.oracle.com/javase/specs/
- **Java SE 15 & JDK 15 API Specification:** https://docs.oracle.com/en/java/javase/15/docs/api/
- **JEP 378 — Text Blocks:** https://openjdk.org/jeps/378
- **JEP 339 — Edwards-Curve Digital Signature Algorithm:** https://openjdk.org/jeps/339
- **JEP 371 — Hidden Classes:** https://openjdk.org/jeps/371

**Nguyên tắc sử dụng lâu dài:** khi gặp một “tính năng Java”, hãy chỉ rõ **cú pháp được JLS định nghĩa**, **API công khai được đặc tả** và/hoặc **hành vi runtime được JVMS yêu cầu hay JVM triển khai riêng**. Việc gọi tên đúng lớp giúp chọn đúng tài liệu, đánh giá tương thích phiên bản và tránh phụ thuộc vào chi tiết không được bảo đảm.
