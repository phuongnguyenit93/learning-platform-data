# Quan hệ giữa ngôn ngữ Java, thư viện chuẩn, công cụ và JVM

Khi viết và chạy một chương trình Java, chúng ta đồng thời sử dụng **quy tắc của ngôn ngữ**, **các API của thư viện chuẩn**, **công cụ phát triển trong JDK** và **môi trường thực thi JVM**. Bốn khái niệm này liên quan chặt chẽ nhưng có trách nhiệm khác nhau. Phân biệt đúng chúng giúp hiểu vì sao mã nguồn biên dịch được, vì sao ứng dụng chạy hoặc không chạy trên một máy, và cần kiểm tra thành phần nào khi gặp lỗi.

Bài học thuộc phần **Định hướng** của lộ trình Java 14; các kiến thức và ví dụ dưới đây tập trung vào những cơ chế vẫn dùng trong phát triển Java hiện đại.

## 1. Mỗi thành phần chịu trách nhiệm gì?

| Thành phần | Bản chất và trách nhiệm | Ví dụ cụ thể |
|---|---|---|
| **Ngôn ngữ Java** | Tập hợp quy tắc về cú pháp, kiểu dữ liệu, biểu thức, câu lệnh và ngữ nghĩa chương trình. Trình biên dịch kiểm tra mã nguồn theo các quy tắc này. | `class`, `int`, `if`, `for`, `new`, generic `<String>`, lambda, method reference, `try`/`catch` |
| **Thư viện chuẩn Java SE** | Các lớp, interface và API được Java SE cung cấp để giải quyết công việc thường gặp. Đây là những API có thể gọi từ mã Java, khác với cú pháp của ngôn ngữ. | `java.lang.String`, `System`, `java.util.List`, `java.time.LocalDate`, `java.nio.file.Files` |
| **JDK (Java Development Kit)** | Bộ công cụ và thành phần cần thiết để phát triển Java: trình biên dịch, lệnh khởi chạy, công cụ đóng gói/phân tích, cùng runtime và thư viện nền tảng. | `javac`, `java`, `jar`, `javadoc`, `jshell`, `javap`, `jdeps`, `jlink` |
| **JVM (Java Virtual Machine)** | Máy ảo thực thi bytecode JVM: nạp và xác minh lớp, liên kết, quản lý bộ nhớ, thực thi phương thức, phối hợp với hệ điều hành. | Nạp `.class`, chạy bytecode bằng bộ thông dịch/JIT tùy bản triển khai, thu gom rác (GC) |

Cần phân biệt thêm ba thuật ngữ:

- **Java SE** là nền tảng và tập đặc tả gồm ngôn ngữ, JVM và các API chuẩn liên quan; **JDK** là một bản phân phối triển khai nền tảng cùng công cụ phát triển.
- **JVM** là thành phần thực thi bên trong runtime Java; nó không phải trình biên dịch mã nguồn Java. `javac` là công cụ biên dịch mã nguồn Java.
- **Maven/Gradle và IDE** là các công cụ bổ trợ nằm ngoài thư viện chuẩn và không đồng nghĩa với JDK. Chúng giúp quản lý dependency, build, kiểm thử hoặc gọi những công cụ JDK.

Một JDK hiện đại đã chứa các thành phần để biên dịch và chạy chương trình thông thường; không cần giả định rằng phải cài thêm một bộ JRE riêng. Khi triển khai, ứng dụng vẫn cần một môi trường thực thi phù hợp, chẳng hạn một JDK/runtime image tương thích.

## 2. Các thành phần phối hợp trong quá trình chạy

Một quy trình điển hình:

~~~text
Mã nguồn .java
  │  Dùng cú pháp Java và tham chiếu API Java SE
  ▼
javac (công cụ của JDK)
  │  Phân tích cú pháp, kiểm tra kiểu và API trên classpath/module path
  ▼
Tệp .class chứa JVM bytecode
  │  java (lệnh khởi chạy; có thể nạp class từ thư mục/JAR/module)
  ▼
JVM
  ├─ Nạp, xác minh và liên kết lớp
  ├─ Thực thi bytecode; có thể biên dịch JIT các đoạn cần tối ưu
  ├─ Quản lý vùng nhớ và garbage collection
  └─ Sử dụng các lớp thư viện runtime và tương tác với OS
  ▼
Kết quả, I/O, tài nguyên hệ thống
~~~

**Điểm cần hiểu đúng:**

1. Mã `.java` là mã nguồn theo ngôn ngữ Java. `javac` thông thường chuyển mã đó thành bytecode trong các tệp `.class`. Bytecode là tập lệnh của JVM, không phải mã máy riêng của Windows, Linux hay macOS.
2. Lệnh `java` khởi động một môi trường thực thi JVM thích hợp. JVM thực hiện nạp, kiểm tra và thực thi bytecode. Một JVM có thể thông dịch hoặc dùng JIT để tối ưu, tùy bản triển khai và trạng thái chạy; không nên mặc định mọi dòng mã đều được JIT biên dịch ngay.
3. Thư viện chuẩn tham gia **cả lúc biên dịch lẫn lúc chạy**: trình biên dịch cần biết kiểu và chữ ký API mà mã gọi; runtime cần có phần triển khai API tương thích để thực thi các lời gọi đó.
4. JDK cũng cung cấp công cụ khác để đóng gói hoặc phân tích, nhưng các công cụ như `jar` và `javap` không phải thành phần thực thi mỗi câu lệnh trong ứng dụng.
5. JVM không chỉ dành cho mã nguồn Java: ngôn ngữ khác có thể có trình biên dịch phát ra bytecode JVM. Vì vậy, “ngôn ngữ Java” và “JVM” là hai khái niệm riêng.

Sơ đồ trên mô tả quy trình biên dịch trước rồi chạy. Một số chế độ tiện lợi có thể biên dịch mã nguồn ngầm khi khởi chạy, nhưng sự phân biệt giữa mã nguồn, bytecode và runtime vẫn hữu ích.

## 3. Phân biệt ngay trong một đoạn mã

Xét biểu thức:

~~~java
List<String> names = List.of("Java", "JVM");
int total = names.stream().mapToInt(String::length).sum();
~~~

- `List`, `String`, `List.of(...)`, `stream()`, `mapToInt(...)`, `length()` và `sum()` thuộc các kiểu/phương thức của **API thư viện chuẩn** (những nơi thích hợp cần import, chẳng hạn `java.util.List`).
- Dấu khai báo biến, kiểu generic `<String>`, phép gán `=` và cú pháp method reference `::` là cách **ngôn ngữ Java** diễn đạt chương trình.
- **`javac`** kiểm tra liệu mã nguồn hợp cú pháp, có đúng kiểu và tìm thấy những phương thức phù hợp hay không.
- **JVM** thực thi các chỉ thị sau biên dịch và gọi phần triển khai những phương thức thư viện liên quan.

Một vài cặp dễ nhầm:

| Thuộc ngôn ngữ | Thuộc thư viện chuẩn |
|---|---|
| Kiểu nguyên thủy `int`, `boolean` | Lớp bao `Integer`, `Boolean` |
| Từ khóa `new` | Lớp được khởi tạo, ví dụ `ArrayList` |
| Cú pháp `try`-with-resources | Interface `AutoCloseable` và các lớp tài nguyên như `Files` |
| Cú pháp lambda `x -> x + 1` | Các functional interface như `Function`, `Predicate` |
| Cú pháp `import` | Tên gói/lớp được import như `java.util.List` |

Ví dụ, `String` **không phải từ khóa Java**: nó là lớp trong `java.lang`. Ngược lại, `int` là kiểu nguyên thủy của ngôn ngữ. Hai thứ có thể phối hợp nhưng không thể đánh đồng.

## 4. Ví dụ đầy đủ có thể biên dịch và chạy

Tạo tệp **`JavaLayersDemo.java`** với nội dung sau (tên tệp phải khớp tên `public class`):

~~~java
import java.util.List;

public class JavaLayersDemo {
    public static void main(String[] args) {
        List<String> names = List.of("Java", "JVM");
        int total = names.stream()
                .mapToInt(String::length)
                .sum();

        System.out.println("Items: " + names.size());
        System.out.println("Characters: " + total);
    }
}
~~~

Dùng JDK 17 hoặc mới hơn có hỗ trợ đích Java 17. Tại thư mục chứa tệp, thực hiện:

~~~bash
javac --release 17 JavaLayersDemo.java
java JavaLayersDemo
~~~

Kết quả chuẩn:

~~~text
Items: 2
Characters: 7
~~~

**Vì sao kết quả này đúng?** `List.of` tạo danh sách chứa hai chuỗi. `size()` trả về `2`. Hai chuỗi `Java` và `JVM` có độ dài lần lượt là `4` và `3`, nên `mapToInt(String::length).sum()` trả về `7`. Mỗi lời gọi `System.out.println` in một dòng.

Nhìn theo từng lớp:

- **Ngôn ngữ:** khai báo `class`, phương thức `main`, generic, khai báo biến, biểu thức và method reference.
- **Thư viện chuẩn:** `List`, `String`, Stream API, `System.out`.
- **Công cụ JDK:** `javac` tạo `JavaLayersDemo.class`; `java` khởi chạy chương trình.
- **JVM:** nạp lớp và thực thi bytecode, cùng các lớp thư viện cần dùng.

Có thể quan sát bytecode bằng công cụ JDK:

~~~bash
javap -c JavaLayersDemo
~~~

Kết quả của `javap` phụ thuộc bản biên dịch và cách trình bày bytecode; đây là công cụ **xem** chỉ thị, không phải lệnh chạy chương trình.

Nếu cần phân phối nhiều tệp `.class` dưới dạng kho lưu trữ, `jar` giúp đóng gói:

~~~bash
jar --create --file demo.jar JavaLayersDemo.class
java -cp demo.jar JavaLayersDemo
~~~

Lệnh thứ hai vẫn khởi chạy JVM và cho ra **hai dòng output như trên**; `jar` là định dạng đóng gói, không tự thay thế runtime.

## 5. Điều kiện tương thích giữa lúc phát triển và lúc chạy

**Khả năng di động của Java** đến từ một mô hình chung: mã được biên dịch thành bytecode theo đặc tả JVM và thực thi bởi JVM tương thích trên hệ điều hành đích. Tuy nhiên, khả năng chạy thực tế còn phụ thuộc phiên bản, API, dependency, hệ điều hành và tài nguyên.

| Thành phần cần khớp | Ý nghĩa thực tế |
|---|---|
| **Phiên bản ngôn ngữ/API đích** | Mã không được dùng cú pháp hay API mới hơn mức phiên bản mà ứng dụng cam kết hỗ trợ. |
| **Định dạng bytecode** | Runtime phải hiểu phiên bản class file được trình biên dịch tạo. Bytecode quá mới có thể gây `UnsupportedClassVersionError`. |
| **Thư viện tại runtime** | API và dependency cần có với phiên bản tương thích. Biên dịch được không bảo đảm runtime có đúng mọi lớp/phương thức. |
| **Môi trường hệ thống** | File path, encoding, quyền truy cập, thư viện native và hành vi phụ thuộc OS có thể làm ứng dụng chạy khác nhau. |

Lệnh `javac --release 17` trong ví dụ yêu cầu trình biên dịch tạo bytecode và giới hạn các API Java SE theo đích Java 17. Đây là cách thiết lập đích tương thích tốt hơn việc chỉ chọn một kiểu cú pháp nguồn. Tùy bản JDK đang dùng, chỉ một số giá trị `--release` được hỗ trợ; phải kiểm tra công cụ thực tế. Tùy chọn này **không** tự biến mọi dependency bên thứ ba thành thư viện chạy được trên Java 17 và không bảo đảm tương thích của toàn bộ hệ thống.

Một quy trình kiểm tra đơn giản:

~~~bash
java -version
javac -version
~~~

Đọc hai kết quả để xác nhận đang dùng runtime và trình biên dịch dự định. Nếu dùng IDE hoặc Gradle/Maven, cũng kiểm tra JDK và mục tiêu biên dịch được cấu hình trong dự án, vì lệnh trong terminal và công cụ build có thể chọn JDK khác nhau.

Cũng cần phân biệt **classpath/module path** với **JVM**: các đường dẫn này giúp công cụ biên dịch và runtime tìm lớp/module của ứng dụng cùng thư viện phụ thuộc; chúng không phải là một loại máy ảo. `java.base` là một module nền tảng chứa các API quan trọng, chẳng hạn `java.lang` và `java.util`.

## 6. Xác định đúng lớp khi gặp sự cố

| Hiện tượng | Lớp liên quan nhất | Hướng kiểm tra đầu tiên |
|---|---|---|
| `javac` báo lỗi cú pháp, sai kiểu hoặc “cannot find symbol” | Ngôn ngữ, API nhìn thấy tại lúc biên dịch hoặc classpath/module path | Cú pháp, import, kiểu, tên phương thức, dependency và mức `--release` |
| `UnsupportedClassVersionError` khi chạy | Tương thích bytecode với runtime JVM | Phiên bản JDK dùng biên dịch và runtime thực tế |
| `ClassNotFoundException` hoặc `NoClassDefFoundError` | Nạp lớp/dependency tại runtime | Thư viện có được đóng gói/đưa đúng vào classpath/module path không |
| `NoSuchMethodError` | API của dependency khác giữa lúc biên dịch và chạy | Phiên bản JAR/module thực sự được nạp |
| `NullPointerException` | Logic chương trình trong lúc thực thi | Giá trị có thể `null`, đường đi dữ liệu và vị trí lỗi trong stack trace |
| Hết bộ nhớ hoặc hiệu năng kém | Chương trình, tài nguyên và cấu hình runtime/JVM | Phân bổ bộ nhớ, số đối tượng, luồng, GC và phép đo trước khi tối ưu |

Đừng quy mọi lỗi runtime cho JVM. JVM có thể đang thực thi đúng chương trình, còn lỗi xuất phát từ dữ liệu đầu vào, logic ứng dụng hoặc phụ thuộc thiếu.

Garbage collector quản lý phần lớn bộ nhớ đối tượng, nhưng **không thay trách nhiệm đóng file, socket hay kết nối**. Dùng `try`-with-resources với tài nguyên hỗ trợ `AutoCloseable` để giải phóng chúng đúng thời điểm.

## 7. Cách áp dụng khi học và phát triển Java

Khi đọc một ví dụ Java, hãy lần lượt tự hỏi:

1. **Cú pháp nào thuộc ngôn ngữ?** Ví dụ `new`, vòng lặp, generic hoặc lambda.
2. **Lớp/phương thức nào thuộc thư viện chuẩn, và đâu là dependency ngoài?** Ví dụ `List` là Java SE, còn API một framework bên thứ ba thì cần dependency riêng.
3. **Công cụ nào biến mã thành artifact?** Xác định trình biên dịch, mục tiêu `--release` và quy trình build.
4. **Môi trường nào chạy artifact?** Xác định runtime/JVM, phiên bản và các lớp/thư viện được đưa vào đường dẫn thực thi.
5. **Lỗi xuất hiện ở giai đoạn nào?** Biên dịch, nạp/liên kết lớp hay đang thực thi để chọn đúng hướng điều tra.

### Tự kiểm tra

**Câu 1.** `System.out.println("Hello")` là cú pháp Java hay thư viện chuẩn?  
**Trả lời:** Cú pháp gọi phương thức thuộc ngôn ngữ; `System`, `out` và `println` là thành phần API thư viện chuẩn được cú pháp đó sử dụng.

**Câu 2.** Chương trình biên dịch thành công trên JDK mới có chắc chạy được bằng JVM cũ không?  
**Trả lời:** Không. Cần tương thích định dạng class file, Java SE API và dependency; nên chọn mục tiêu biên dịch phù hợp và chạy thử trên runtime đích.

**Câu 3.** Cài Maven/Gradle có thay việc cài một JDK phù hợp không?  
**Trả lời:** Không. Build tool điều phối tác vụ và dependency, nhưng vẫn cần toolchain/compiler và runtime Java phù hợp (có thể được toolchain tự tìm hoặc cấp phát).

**Câu 4.** Tại sao `String`, `int` và JVM là ba thứ khác nhau?  
**Trả lời:** `String` là lớp thư viện chuẩn, `int` là kiểu nguyên thủy trong ngôn ngữ, còn JVM là môi trường thực thi bytecode.

Giữ rõ bốn vai trò trên sẽ giúp bạn lựa chọn API, thiết lập build, xử lý sai khác giữa môi trường và đọc thông báo lỗi theo đúng giai đoạn mà chúng phát sinh.