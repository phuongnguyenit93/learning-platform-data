# Java SE, OpenJDK, JDK và JVM: vai trò và mối liên hệ

Khi bắt đầu học Java 17, bạn sẽ thường gặp bốn tên gọi **Java SE**, **OpenJDK**, **JDK** và **JVM**. Chúng liên quan chặt chẽ nhưng không cùng một loại khái niệm: có thứ là **tiêu chuẩn**, có thứ là **mã nguồn hiện thực tiêu chuẩn**, có thứ là **bộ phần mềm cài lên máy**, và có thứ là **thành phần thực thi chương trình**.

Hiểu đúng sự khác nhau này giúp bạn trả lời những câu hỏi thực tế: Cần cài gì để viết chương trình Java 17? Vì sao có nhiều nhà cung cấp JDK? Khi triển khai lên máy chủ có cần `javac`? Vì sao tệp `.class` chạy được trên nhiều hệ điều hành nhưng vẫn cần JVM tương ứng?

## 1. Nhìn tổng thể: bốn khái niệm, bốn vai trò

| Khái niệm | Bản chất | Vai trò chính |
| --- | --- | --- |
| **Java SE 17** (*Java Platform, Standard Edition*) | Bộ đặc tả/tiêu chuẩn của nền tảng Java phiên bản 17 | Xác định ngôn ngữ Java, hành vi JVM và các API chuẩn mà một bản hiện thực phù hợp cần cung cấp. |
| **OpenJDK 17** (*Open Java Development Kit*) | Dự án và cơ sở mã nguồn mở hiện thực Java SE | Cung cấp phần lớn mã nguồn để xây dựng JDK, gồm trình biên dịch, thư viện chuẩn và JVM HotSpot. |
| **JDK 17** (*Java Development Kit*) | Bộ phần mềm dùng để phát triển và chạy ứng dụng Java 17 | Cung cấp `javac`, `java`, các công cụ khác và môi trường thực thi cần thiết. |
| **JVM** (*Java Virtual Machine*) | Máy ảo thực thi bytecode Java | Nạp, kiểm tra và thực thi mã `.class`; quản lý những cơ chế chạy chương trình như bộ nhớ và thu gom rác. |

Một cách nhớ nhanh:

- **Java SE trả lời:** “Một nền tảng Java 17 đúng chuẩn phải có hành vi và API nào?”
- **OpenJDK trả lời:** “Mã nguồn nào hiện thực nền tảng đó?”
- **JDK trả lời:** “Tôi cài bộ công cụ nào để viết, biên dịch, đóng gói và chạy Java?”
- **JVM trả lời:** “Thành phần nào thực sự thực thi bytecode Java?”

## 2. Java SE 17: nền tảng được định nghĩa bằng tiêu chuẩn

**Java SE** là phiên bản tiêu chuẩn của nền tảng Java, bao gồm các quy tắc ngôn ngữ và các thành phần cần thiết để viết, biên dịch, chạy chương trình Java phổ thông. “Java SE 17” nói đến **phiên bản 17 của nền tảng/đặc tả**, không phải một ứng dụng riêng mà bạn tải về rồi khởi chạy.

Ba nhóm đặc tả quan trọng là:

1. **Java Language Specification (JLS):** quy định cú pháp và ngữ nghĩa của ngôn ngữ; chẳng hạn cách khai báo lớp, kiểu dữ liệu, biểu thức, kế thừa, ngoại lệ.
2. **Java Virtual Machine Specification (JVMS):** quy định định dạng tệp lớp (`.class`), tập lệnh bytecode và mô hình thực thi JVM. Nó định nghĩa hành vi cần tuân thủ, không bắt buộc mọi JVM có kiến trúc nội bộ giống nhau.
3. **Java SE API:** quy định các thư viện chuẩn để ứng dụng sử dụng, chẳng hạn `java.lang`, `java.util`, `java.time`, `java.nio.file`, `java.net.http` và `java.util.concurrent`.

Ví dụ, khi viết:

```java
import java.time.LocalDate;
import java.util.List;

public class StandardApiExample {
    public static void main(String[] args) {
        List<String> languages = List.of("Java", "Kotlin");
        System.out.println(languages);
        System.out.println(LocalDate.now());
    }
}
```

`List` và `LocalDate` thuộc API chuẩn Java SE, nên bạn không cần cài thêm thư viện bên thứ ba để sử dụng chúng trên một JDK 17 đầy đủ. Ngược lại, các framework như Spring hoặc thư viện của ứng dụng là các phụ thuộc riêng; chúng không tự nhiên trở thành một phần của Java SE.

**Điểm phân biệt quan trọng:** đặc tả đưa ra *hợp đồng về hành vi*; một JDK cụ thể cung cấp *mã thực thi và các API* tuân theo hợp đồng đó. Vì vậy, “lập trình theo Java SE 17” và “cài một bản JDK 17” là hai việc liên quan nhưng khác nhau.

## 3. OpenJDK 17: dự án mã nguồn mở hiện thực Java SE

**OpenJDK** là dự án mã nguồn mở phát triển một bản hiện thực của nền tảng Java SE. Dự án này bao gồm nhiều thành phần mà người lập trình sử dụng hằng ngày:

- **`javac`:** trình biên dịch mã nguồn Java thành bytecode.
- **Thư viện và mô-đun chuẩn:** hiện thực các API như `java.base`, `java.sql`, `java.net.http`.
- **HotSpot:** một bản hiện thực JVM phổ biến, có các cơ chế thông dịch, biên dịch JIT, quản lý bộ nhớ và thu gom rác.
- **Các công cụ khác:** `jar`, `javadoc`, `jdeps`, `jlink`, `jshell`, v.v.

Cần phân biệt **dự án/mã nguồn OpenJDK** với **bản phân phối JDK được xây dựng từ mã nguồn OpenJDK**. Những bản phân phối như Eclipse Temurin, Amazon Corretto, Azul Zulu, Microsoft Build of OpenJDK hoặc Oracle JDK có thể cùng dựa phần lớn vào OpenJDK nhưng khác nhau ở cách đóng gói, lịch cập nhật, chính sách hỗ trợ, giấy phép và đôi khi ở các thành phần bổ sung.

Vì thế:

- **OpenJDK không đồng nghĩa với riêng JVM:** mã nguồn của dự án còn có compiler, thư viện chuẩn và công cụ phát triển.
- **OpenJDK không phải tên của mọi tệp cài đặt JDK:** bạn có thể cài một bản JDK do một nhà cung cấp đóng gói từ OpenJDK.
- **Dùng một bản JDK khác nhà cung cấp không nhất thiết làm đổi ngôn ngữ Java:** điều cần quan tâm là phiên bản Java SE, tính tương thích, hệ điều hành/kiến trúc máy và chính sách cập nhật.

Trong phạm vi học Java 17, một bản phân phối **JDK 17 tương thích Java SE 17** là lựa chọn thông dụng để phát triển, bất kể bạn dùng IDE hay dòng lệnh.

## 4. JDK 17: bộ công cụ thực tế cài trên máy

**JDK** là bộ phát triển Java. Khi cài JDK 17, bạn có cả công cụ để tạo chương trình và các thành phần để chạy chương trình Java.

| Thành phần trong JDK | Công dụng |
| --- | --- |
| `javac` | Biên dịch mã nguồn `.java` thành tệp `.class`. |
| `java` | Trình khởi chạy: bắt đầu quá trình thực thi ứng dụng, tạo/khởi động JVM theo cấu hình phù hợp. |
| `jar` | Tạo, xem và thao tác với tệp lưu trữ JAR. |
| `javadoc` | Sinh tài liệu API từ chú thích và mã nguồn. |
| `javap` | Xem thông tin/bytecode trong tệp lớp đã biên dịch. |
| `jshell` | Thử nhanh các biểu thức và đoạn mã Java tương tác. |
| `jdeps` | Phân tích phụ thuộc của lớp/JAR/mô-đun. |
| `jlink` | Tạo ảnh runtime tùy chỉnh từ các mô-đun cần thiết. |
| **Runtime của JDK** | Gồm JVM, thư viện chuẩn và các thành phần cần thiết để thực thi ứng dụng. |

Với Java hiện đại, môi trường chạy có cấu trúc **mô-đun** (có từ Java 9); ví dụ, `java.base` là mô-đun nền tảng luôn có trong runtime Java SE. Bạn có thể chạy ứng dụng bằng runtime đi kèm JDK, hoặc đóng gói một **runtime image** phù hợp bằng `jlink` cho việc triển khai.

### Cần hiểu thế nào về JRE?

**JRE** (*Java Runtime Environment*) là tên gọi truyền thống của môi trường **chạy** Java, đối lập với JDK có thêm công cụ **phát triển**. Trong các hướng dẫn cũ, JRE thường được giới thiệu như một bộ cài riêng.

Đối với Java 17, cách hiểu hữu ích và còn áp dụng là: **ứng dụng cần một runtime có JVM và các mô-đun/thư viện cần thiết; người biên dịch cần JDK**. Runtime đó có thể đi kèm JDK hoặc được cung cấp/đóng gói riêng. Không nên mặc định phải tìm một bộ cài “JRE 17” độc lập chỉ vì các tài liệu cũ từng hướng dẫn như vậy.

### JDK trên máy lập trình và trên máy chạy

- **Máy lập trình/CI build:** cần JDK để chạy `javac` và các công cụ build.
- **Máy chạy ứng dụng đã biên dịch:** không nhất thiết cần `javac`; cần một runtime tương thích và đầy đủ các mô-đun/phụ thuộc của ứng dụng. Cài trọn JDK cũng có thể chạy chương trình, nhưng không phải lựa chọn duy nhất.
- **IDE như IntelliJ IDEA hoặc VS Code:** IDE là công cụ hỗ trợ biên tập, điều hướng, debug; nó cần trỏ tới JDK phù hợp với dự án để biên dịch/chạy Java 17.

## 5. JVM: bộ máy thực thi bytecode

**JVM** cung cấp môi trường thực thi những tệp lớp Java đã biên dịch. Đường đi cơ bản khi khởi chạy một ứng dụng gồm:

1. **Nạp lớp:** class loader tìm và nạp các lớp cần thiết từ classpath/module path và runtime.
2. **Liên kết và kiểm tra:** JVM kiểm tra tính hợp lệ của bytecode và chuẩn bị cấu trúc lớp theo quy tắc của JVM.
3. **Khởi tạo lớp và thực thi:** chạy mã cần thiết, gọi `main` hoặc điểm vào phù hợp.
4. **Tối ưu khi chạy:** một JVM như HotSpot có thể thông dịch bytecode và biên dịch JIT (*Just-In-Time*) các đoạn mã được thực thi thường xuyên thành mã máy.
5. **Quản lý thời gian chạy:** cấp phát/quản lý bộ nhớ, thu gom rác, đồng bộ hóa luồng và xử lý ngoại lệ theo ngữ nghĩa Java.

**JVM không phải chính là lệnh `javac`.** `javac` chạy trước để tạo bytecode; JVM xử lý bytecode trong lúc chạy chương trình. Lệnh `java` là *launcher* dùng để khởi động quá trình thực thi; nó không phải tên gọi của toàn bộ JVM.

### Bytecode giúp ứng dụng có tính di động như thế nào?

Một tệp `.class` chứa **bytecode JVM**, không phải mã máy chỉ dành cho Windows, Linux hay macOS. Nếu có runtime Java phù hợp trên từng hệ điều hành/kiến trúc, JVM tương ứng sẽ thực thi bytecode đó.

```text
Mã nguồn Java 17 (.java)
          |
          | javac (trình biên dịch trong JDK 17)
          v
Bytecode JVM (.class, phiên bản class file 61)
          |
          | java (trình khởi chạy)
          v
JVM phù hợp + thư viện runtime
          |
          | thông dịch / JIT / sử dụng dịch vụ hệ điều hành
          v
Chương trình thực thi trên máy đích
```

Tính di động có **điều kiện**: runtime phải hỗ trợ phiên bản class file và API mà chương trình sử dụng; thư viện native, đường dẫn tệp, cấu hình hệ điều hành hoặc phần phụ thuộc bên ngoài vẫn có thể khiến ứng dụng cần điều chỉnh theo môi trường.

Với bytecode được biên dịch cho **Java 17**, số phiên bản class file (*major version*) là **61**. JVM của Java cũ hơn, chẳng hạn Java 11, không thể nạp trực tiếp tệp lớp phiên bản 61; một triệu chứng thường thấy là `UnsupportedClassVersionError`.

## 6. Mối liên hệ giữa Java SE, OpenJDK, JDK và JVM

Hãy nhìn cùng lúc vào hai chiều: **cái gì định nghĩa/cung cấp nền tảng** và **chương trình đi qua các thành phần nào khi chạy**.

```text
Java SE 17
(đặc tả ngôn ngữ, JVM và API)
      |
      | được hiện thực bởi
      v
OpenJDK 17
(mã nguồn javac, thư viện, HotSpot, công cụ ...)
      |
      | các nhà cung cấp xây dựng, đóng gói, cập nhật
      v
Bản phân phối JDK 17
      |                              |
      +-- Công cụ phát triển         +-- Môi trường chạy
          javac, jar, javadoc, ...       java launcher
                                       JVM (thường là HotSpot)
                                       Thư viện/mô-đun Java SE
```

Sơ đồ thể hiện một nhánh triển khai phổ biến từ mã nguồn OpenJDK; khái niệm Java SE không lệ thuộc vào duy nhất một nhà cung cấp. Bên trong một bản JDK, **JVM là thành phần runtime**, còn JDK là **bộ sản phẩm lớn hơn** bao gồm cả công cụ phát triển.

Một chương trình Java 17 sử dụng cả chuỗi đó: viết theo quy tắc Java SE 17; dùng `javac` từ một JDK 17 để biên dịch; dùng `java` khởi chạy JVM trong runtime phù hợp; khi chạy thì gọi thư viện chuẩn do runtime cung cấp.

## 7. Thực hành: từ mã nguồn đến JVM trên Java 17

Giả sử bạn đã cài một bản phân phối JDK 17 và cấu hình terminal dùng đúng bản JDK đó.

### Bước 1: Kiểm tra môi trường

Chạy:

```bash
java -version
javac -version
```

Lệnh đầu cho biết runtime Java được terminal tìm thấy; lệnh sau cho biết phiên bản compiler. Trong bài học này, cả hai cần trỏ về **Java 17**. Kết quả thực tế có thể kèm tên nhà cung cấp, bản cập nhật `17.0.x` hoặc tên JVM.

Nếu `java` chạy được nhưng `javac` không được nhận diện, có thể terminal đang trỏ tới runtime không có compiler, hoặc biến môi trường `PATH` chưa chứa thư mục `bin` của JDK cần dùng. `JAVA_HOME` (khi công cụ yêu cầu) thường trỏ đến **thư mục gốc của JDK**, không trỏ đến tệp `java` và không phải chỉ đến thư mục `bin`.

### Bước 2: Viết một chương trình nhỏ

Tạo tệp **`HelloJava17.java`**:

```java
public class HelloJava17 {
    public static void main(String[] args) {
        System.out.println("Java version: " + Runtime.version().feature());
        System.out.println("Xin chao Java 17!");
    }
}
```

`Runtime.version().feature()` là API có sẵn trong Java SE; khi chạy bằng runtime Java 17, giá trị được in là `17`.

### Bước 3: Biên dịch và chạy

Tại thư mục chứa tệp nguồn:

```bash
javac HelloJava17.java
java HelloJava17
```

Kết quả minh họa:

```text
Java version: 17
Xin chao Java 17!
```

Đây là hai thao tác khác nhau:

1. `javac HelloJava17.java` dùng **compiler của JDK** để sinh `HelloJava17.class`.
2. `java HelloJava17` dùng **launcher** để khởi động JVM, tìm lớp `HelloJava17` và thực thi phương thức `main`.

Lưu ý lệnh chạy dùng **tên lớp** `HelloJava17`, không cần thêm đuôi `.class`.

Bạn có thể xem metadata của class file bằng công cụ JDK:

```bash
javap -verbose HelloJava17.class
```

Trong đầu ra sẽ có `major version: 61` nếu tệp được biên dịch để chạy trên Java 17.

### Bước 4: Phân biệt chế độ chạy trực tiếp tệp nguồn

Java 17 cũng hỗ trợ chạy chương trình ở chế độ *source-file mode*:

```bash
java HelloJava17.java
```

Ở chế độ này, launcher xử lý việc biên dịch mã nguồn để thực thi trong cùng một lần gọi; bạn không phải tự chạy `javac` trước. Đây là tiện ích khi thử chương trình nhỏ, **không có nghĩa JVM tự hiểu và chạy trực tiếp cú pháp Java**: mã nguồn vẫn phải được biên dịch thành dạng thực thi phù hợp.

### Bước 5: Khi muốn biên dịch nhắm tới Java 17

Nếu bạn đang dùng một JDK mới hơn để build cho môi trường Java 17, sử dụng:

```bash
javac --release 17 HelloJava17.java
```

Tùy chọn `--release 17` yêu cầu compiler nhắm tới mức ngôn ngữ, class file và API chuẩn của Java 17. **`--release` không thay thế việc kiểm tra các thư viện phụ thuộc hoặc chạy thử trên runtime đích.** Với compiler JDK 17 khi không chỉ định tùy chọn khác, mục tiêu mặc định đã là Java 17.

## 8. Chọn đúng thành phần trong tình huống thực tế

| Tình huống | Thành phần cần quan tâm | Giải thích |
| --- | --- | --- |
| Bắt đầu học Java 17 trên laptop | **Bản phân phối JDK 17** | Có `javac` để biên dịch và runtime để chạy ví dụ. |
| Đọc tài liệu `java.util` hoặc cú pháp `switch` | **Java SE 17** | Đặc tả và API cho biết điều gì được hỗ trợ trong phiên bản 17. |
| So sánh Eclipse Temurin và Amazon Corretto 17 | **Bản phân phối dựa trên OpenJDK** | Xem chính sách cập nhật, bảo mật, hỗ trợ, giấy phép và nền tảng được hỗ trợ. |
| Ứng dụng chạy chậm hoặc cần điều chỉnh garbage collector | **JVM cụ thể và runtime** | JVM thực thi chương trình và cung cấp các cơ chế tối ưu/GC; tùy chọn có thể khác theo bản hiện thực. |
| Build chương trình bằng CI | **JDK và phiên bản compiler** | Dùng toolchain đúng phiên bản, không chỉ nhìn phiên bản Java trên máy cá nhân. |
| Chạy ứng dụng Java đã đóng gói | **Runtime tương thích** | Cần JVM và các mô-đun/thư viện ứng dụng dùng; compiler không bắt buộc trên máy đích. |
| Đóng gói runtime gọn cho ứng dụng có mô-đun | **`jlink` trong JDK** | Tạo runtime image chứa những mô-đun được chọn. |

## 9. Những nhầm lẫn thường gặp

**“Java SE 17 chính là một bản JDK để tải.”** Không đúng về mặt khái niệm. Java SE là nền tảng/đặc tả; JDK 17 là bộ phần mềm hiện thực để bạn sử dụng nền tảng ấy.

**“OpenJDK chỉ là một JVM.”** Không đúng. OpenJDK bao gồm cả trình biên dịch, thư viện Java SE, các công cụ phát triển và bản hiện thực JVM HotSpot.

**“JDK và JVM là hai tên gọi thay thế nhau.”** Không đúng. JVM là bộ máy thực thi bytecode; JDK bao gồm JVM/runtime cùng các công cụ như `javac`.

**“Tôi đã cài `java` nên chắc chắn có `javac`.”** Chưa chắc. Cần kiểm tra riêng cả hai lệnh và đường dẫn cài đặt, nhất là khi máy có nhiều bản Java.

**“Ứng dụng Java chạy ở đâu cũng được mà không cần kiểm tra phiên bản.”** Không đúng. Bytecode Java 17 yêu cầu JVM đủ mới để hiểu class file tương ứng; ngoài ra còn có phụ thuộc thư viện, mô-đun, cấu hình và hệ điều hành.

**“Muốn chạy Java 17 thì bắt buộc phải tìm bản cài JRE riêng.”** Không đúng. Runtime đi cùng JDK 17 có thể chạy chương trình; với một số trường hợp triển khai có thể dùng runtime image được đóng gói phù hợp.

**“Spring Boot, Jakarta EE và Java SE là cùng một tầng.”** Không đúng. Java SE là nền tảng chuẩn cơ sở; các framework và nền tảng ứng dụng khác có phạm vi, API và hệ sinh thái riêng, thường hoạt động trên nền một JDK/runtime Java tương thích.

## 10. Tự kiểm tra mức hiểu

1. **Nếu chỉ muốn biên dịch một tệp `Hello.java`, công cụ nào làm việc đó?** → `javac` trong JDK.
2. **Nếu chỉ có tệp `Hello.class`, thành phần nào chạy bytecode?** → JVM được khởi động qua launcher `java` trong một runtime tương thích.
3. **Nếu hỏi `List.of(...)` có thuộc API Java 17 không, cần tra ở đâu?** → Đặc tả và tài liệu API Java SE 17.
4. **Nếu máy dùng Temurin 17 còn máy khác dùng Corretto 17, chúng có thể cùng chạy một chương trình Java SE 17 không?** → Thông thường có, nếu chương trình và các phụ thuộc tương thích với cả hai môi trường.
5. **Nếu biên dịch cho Java 17 rồi đem chạy trên Java 11, lỗi có thể bắt nguồn từ đâu?** → JVM Java 11 không hỗ trợ class file phiên bản 61 do Java 17 tạo.

Khi gặp một vấn đề Java, hãy xác định nó nằm ở **quy tắc/API của Java SE**, **mã nguồn hoặc bản phân phối OpenJDK**, **công cụ trong JDK**, hay **khả năng thực thi của JVM**. Việc xác định đúng tầng sẽ giúp bạn chọn đúng tài liệu, đúng cấu hình và đúng công cụ xử lý.

## Tài liệu chính thức để tra cứu

- [Java Language Specification, Java SE 17](https://docs.oracle.com/javase/specs/jls/se17/html/index.html)
- [Java Virtual Machine Specification, Java SE 17](https://docs.oracle.com/javase/specs/jvms/se17/html/index.html)
- [Java SE 17 API Documentation](https://docs.oracle.com/en/java/javase/17/docs/api/index.html)
- [OpenJDK — JDK 17 Project](https://openjdk.org/projects/jdk/17/)
- [JDK 17 Tool Specifications](https://docs.oracle.com/en/java/javase/17/docs/specs/man/index.html)
