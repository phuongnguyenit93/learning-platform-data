# JVM là gì và vì sao Java cần một máy thực thi trung gian?

## 1. Vấn đề Java cần giải quyết

Máy tính cuối cùng thực thi **lệnh máy** phù hợp với kiến trúc CPU và hệ điều hành. Chương trình viết bằng Java lại được biểu diễn dưới dạng mã nguồn (`.java`), một dạng con người có thể đọc và biên dịch. Nếu biên dịch mã nguồn thành lệnh máy riêng cho từng hệ thống, nhà phát triển phải tạo và phân phối những bản thực thi khác nhau cho nhiều môi trường.

Java chọn một mô hình có **lớp thực thi trung gian**:

```text
Mã nguồn Java (.java)
          |
          | javac (trình biên dịch của JDK)
          v
Bytecode Java (.class, có thể đóng gói trong .jar)
          |
          | JVM tương thích: nạp lớp → kiểm tra → thực thi
          v
Lệnh máy chạy trên CPU và dịch vụ của hệ điều hành
```

Chương trình được biên dịch một lần thành **bytecode**, tức tập lệnh dành cho *máy ảo Java* thay vì trực tiếp cho một CPU cụ thể. Mỗi nền tảng cần một bản triển khai JVM phù hợp; bản JVM đó đảm nhận việc thực thi bytecode trên nền tảng của mình. Đây là cơ sở của ý tưởng **“write once, run anywhere”** (viết một lần, chạy trên nhiều môi trường tương thích).

Điểm cốt lõi: JVM giúp tách **mã chương trình đã biên dịch** khỏi **chi tiết thực thi của từng hệ thống**. Tính di động này có điều kiện: môi trường đích phải cung cấp JVM tương thích với phiên bản bytecode và các thư viện mà ứng dụng cần.

## 2. JVM thực chất là gì?

**JVM (Java Virtual Machine)** là mô hình máy tính trừu tượng được đặc tả để nạp, kiểm tra và thực thi tệp lớp Java (`.class`). Một **bản triển khai JVM** là phần mềm hiện thực hóa mô hình đó, làm việc cùng hệ điều hành và phần cứng thật. Ví dụ, **HotSpot** là một bản triển khai JVM phổ biến trong các bản phân phối OpenJDK; không phải mọi JVM đều sử dụng cùng một trình biên dịch JIT hay cùng thuật toán quản lý bộ nhớ.

Cần phân biệt ba lớp:

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| **Ngôn ngữ Java** | Quy tắc viết mã nguồn: kiểu, cú pháp, lớp, biểu thức… | `class`, `interface`, `try` |
| **Bytecode / định dạng class** | Dạng mã biên dịch cho JVM và định dạng mang thông tin kiểu, phương thức, hằng số… | `Hello.class` |
| **JVM** | Môi trường thực thi các lớp đã biên dịch theo đặc tả JVM | HotSpot, OpenJ9 |

JVM **không phải** trình biên dịch nguồn `javac`, **không phải** bản thân hệ điều hành, và **không phải** toàn bộ hệ sinh thái Java. Nó là một thành phần runtime trung tâm. Cũng vì bytecode là giao diện thực thi, một số ngôn ngữ khác như Kotlin hoặc Scala có thể biên dịch thành mã chạy trên JVM.

Một mô tả cụ thể hơn: khi chạy `java TenLop`, công cụ khởi chạy Java thiết lập môi trường và khởi tạo JVM phù hợp, JVM nạp những lớp cần thiết rồi thực thi điểm vào chương trình (thường là phương thức `main`). Một tiến trình Java thông thường có một JVM đang chạy, nhưng không nên hiểu rằng “mỗi đối tượng Java là một máy ảo” hay mọi hệ thống đều chỉ có duy nhất một JVM.

## 3. Vì sao cần máy thực thi trung gian?

### 3.1. Tính di động giữa các nền tảng

Một tệp `.class` hợp lệ chứa lệnh bytecode, không chứa trực tiếp bộ lệnh x86-64 hay ARM64 cho CPU cụ thể. JVM trên Windows, Linux hay macOS có thể hiểu cùng định dạng đó khi đáp ứng yêu cầu về phiên bản và thư viện. Nhà phát triển thường không phải biên dịch lại mã Java cho mỗi hệ điều hành chỉ vì CPU khác nhau.

**Nhưng “chạy mọi nơi” không phải lời hứa tuyệt đối.** Chương trình vẫn có thể phụ thuộc vào đường dẫn tệp, quyền truy cập, biến môi trường, thư viện native qua JNI, giao diện đồ họa, cấu hình thời gian/vùng miền hoặc các API chỉ có ở một hệ điều hành. Một class biên dịch cho phiên bản Java mới có thể không chạy trên JVM cũ.

### 3.2. Một hợp đồng thực thi thống nhất

Đặc tả JVM quy định định dạng tệp class, tập lệnh bytecode, các vùng dữ liệu lúc chạy, cơ chế nạp và liên kết lớp, cùng nhiều quy tắc thực thi. Nhờ đó, trình biên dịch và runtime có một hợp đồng rõ ràng: trình biên dịch tạo bytecode hợp lệ, JVM triển khai ý nghĩa của bytecode.

Lớp trung gian cũng giúp các công cụ phân tích bytecode, kiểm thử, đo hiệu năng, theo dõi lỗi và các ngôn ngữ JVM khác làm việc trên một nền tảng chung.

### 3.3. Tối ưu trong lúc chương trình chạy

Một JVM hiện đại có thể bắt đầu thực thi bytecode bằng **trình thông dịch (interpreter)** rồi dùng **JIT compiler** (*Just-In-Time*) để chuyển các phần mã thường xuyên thực thi thành mã máy phù hợp CPU hiện tại. Runtime có thể thu thập thông tin khi chương trình chạy để quyết định tối ưu hóa, ví dụ inline lời gọi phương thức trong những điều kiện thích hợp.

Tùy JVM và cách cấu hình, chiến lược thực thi có thể khác nhau; **không phải mọi bytecode đều bắt buộc được JIT biên dịch**. Quyết định tối ưu có thể được thay đổi hoặc hủy khi các giả định runtime không còn đúng (*deoptimization*).

### 3.4. Quản lý runtime chung

JVM cung cấp những cơ chế nền tảng để ứng dụng có thể hoạt động thống nhất hơn:

- **Nạp và liên kết lớp:** tìm, kiểm tra, chuẩn bị và sử dụng các định nghĩa lớp khi cần.
- **Quản lý bộ nhớ:** cấp phát đối tượng và phối hợp thu gom rác (*garbage collection*) trong các JVM thông dụng.
- **Thực thi phương thức, ngoại lệ và luồng:** duy trì ngữ cảnh chạy, ngăn xếp lời gọi, xử lý ngoại lệ và phối hợp với hệ điều hành.
- **Kiểm tra bytecode:** giúp ngăn nhiều loại mã class sai cấu trúc hoặc vi phạm ràng buộc kiểu được thực thi.

Các cơ chế này không đồng nghĩa với việc JVM tự động ngăn mọi lỗi, rò rỉ tài nguyên native hoặc lỗ hổng bảo mật trong ứng dụng.

## 4. JVM tham gia vào vòng đời chương trình như thế nào?

Có thể chia quá trình thành hai thời điểm khác nhau.

**Thời điểm biên dịch** (trước khi chạy):

1. Lập trình viên viết tệp `.java`.
2. Trình biên dịch `javac` phân tích mã nguồn, kiểm tra kiểu theo ngôn ngữ Java và tạo tệp `.class`.
3. Class có thể được đóng gói trong JAR để phân phối. JAR về cơ bản là tệp lưu trữ; **nó không phải JVM**.

**Thời điểm thực thi**:

1. Trình khởi chạy `java` thiết lập đường dẫn lớp/module và bắt đầu runtime.
2. **Class loader** nạp các lớp cần thiết. Không nhất thiết mọi lớp trong ứng dụng đều được nạp ngay khi khởi động.
3. JVM **liên kết** lớp: xác minh bytecode (`verification`), chuẩn bị cấu trúc dữ liệu (`preparation`) và giải quyết tham chiếu ký hiệu (`resolution`, có thể được trì hoãn trong giới hạn đặc tả).
4. JVM **khởi tạo** lớp khi các điều kiện tương ứng xảy ra, gồm việc thực hiện những phần khởi tạo tĩnh cần thiết.
5. Runtime thực thi bytecode bằng cơ chế phù hợp của bản JVM (thông dịch, biên dịch JIT hoặc kết hợp), gọi dịch vụ hệ điều hành khi cần.
6. Trong quá trình chạy, runtime quản lý đối tượng, ngăn xếp lời gọi, ngoại lệ và phối hợp với hệ điều hành. Khi chương trình kết thúc, các tài nguyên của tiến trình được giải phóng theo cơ chế của hệ điều hành.

Mô hình đơn giản:

```text
                    +----------------------------------+
.class  ----------> | JVM đang chạy                     |
                    |  Nạp lớp và kiểm tra bytecode    |
                    |  Runtime data areas              |
                    |  Interpreter / JIT (tùy JVM)     |
                    |  Garbage collector (tùy JVM)     |
                    +----------------+-----------------+
                                     |
                                     v
                        Hệ điều hành + CPU thật
```

Sơ đồ trên là mô hình khái niệm. Nó không có nghĩa class loader, JIT và bộ thu gom rác luôn chạy theo một chuỗi tuần tự cố định; nhiều hoạt động được thực hiện theo nhu cầu hoặc đồng thời.

## 5. Ví dụ Java 17+: cùng chương trình, JVM thực thi bytecode

Tạo tệp **`BytecodeDemo.java`**:

```java
public class BytecodeDemo {
    public static int sum(int a, int b) {
        return a + b;
    }

    public static void main(String[] args) {
        System.out.println(sum(2, 3));
    }
}
```

Trong terminal có JDK 17 trở lên, đứng tại thư mục chứa tệp rồi chạy:

```bash
javac BytecodeDemo.java
java BytecodeDemo
```

**Kết quả chuẩn của lệnh `java BytecodeDemo`:**

```text
5
```

Lệnh `javac` tạo **`BytecodeDemo.class`**. Lệnh `java` mới khởi chạy chương trình trên JVM; không cần biên dịch lại từ `.java` ở mỗi lần chạy nếu class vẫn phù hợp.

Dùng công cụ `javap` của JDK để quan sát bytecode:

```bash
javap -c BytecodeDemo
```

Trong phần phương thức `sum(int, int)` sẽ có đoạn tương đương sau (lược bỏ phần khác của kết quả `javap`):

```text
public static int sum(int, int);
  Code:
     0: iload_0
     1: iload_1
     2: iadd
     3: ireturn
```

Ý nghĩa:

- `iload_0` và `iload_1`: đưa hai đối số kiểu `int` lên ngăn xếp toán hạng.
- `iadd`: cộng hai số nguyên `int` trên ngăn xếp.
- `ireturn`: trả kết quả kiểu `int` về phương thức gọi.

Đây là **lệnh bytecode của JVM**, không phải câu lệnh hợp ngữ riêng cho CPU x86 hay ARM. Các lệnh bytecode khác trong `main` thực hiện gọi `sum` và in kết quả. Một JVM tương thích sẽ gán ý nghĩa nhất quán cho các opcode này, dù cách triển khai thành lệnh máy ở từng môi trường có thể khác.

**Tự quan sát phiên bản runtime:**

```bash
java -version
javac -version
```

Đầu ra phụ thuộc vào bản JDK/JVM cài đặt, nên không có một chuỗi phiên bản cố định áp dụng cho mọi máy. Nếu máy chỉ có môi trường chạy nhưng thiếu công cụ biên dịch, có thể chạy tệp class đã được biên dịch phù hợp mà không có `javac` tại môi trường đích.

### Không nhầm ba hình thức thực thi

| Cách chạy | Đầu vào chính | Điều diễn ra |
| --- | --- | --- |
| `javac BytecodeDemo.java` | Mã nguồn Java | Biên dịch ra bytecode `BytecodeDemo.class`; không chạy `main` |
| `java BytecodeDemo` | Class có sẵn trên classpath | Khởi chạy JVM và thực thi chương trình |
| `javap -c BytecodeDemo` | Class đã biên dịch | Phân tích/hiển thị bytecode; không thực thi `main` |

Một số phiên bản Java còn hỗ trợ chạy trực tiếp tệp nguồn bằng lệnh `java File.java`. Đây là tiện ích của trình khởi chạy; về bản chất vẫn có bước biên dịch và cơ chế thực thi bytecode thích hợp, không phủ nhận vai trò của JVM.

## 6. Điều gì diễn ra trong bộ nhớ JVM?

Đặc tả JVM mô tả những **runtime data areas** chính; cách cấp phát vật lý và tối ưu hóa thuộc về từng bản triển khai.

| Vùng dữ liệu | Ý nghĩa cơ bản |
| --- | --- |
| **Heap** | Chứa đối tượng và mảng; thường được chia sẻ giữa các luồng của cùng JVM, và là đối tượng quản lý của bộ thu gom rác |
| **Java Virtual Machine Stack** | Mỗi luồng có ngăn xếp gồm các *frame* cho từng lời gọi phương thức Java, gồm biến cục bộ, ngăn xếp toán hạng và dữ liệu thực thi liên quan |
| **PC register** | Mỗi luồng có bộ đếm chương trình gắn với lệnh JVM đang thực thi (với phương thức native, trạng thái được đặc tả khác) |
| **Method area** | Vùng logic dùng chung cho cấu trúc lớp như dữ liệu phương thức và thông tin runtime; cách hiện thực phụ thuộc JVM |
| **Native method stack** | Hỗ trợ lời gọi phương thức native nếu bản JVM sử dụng cơ chế ngăn xếp này |

Trong HotSpot, **Metaspace** là một cơ chế triển khai quan trọng cho metadata lớp, nhưng không nên đồng nhất toàn bộ khái niệm *method area* trong đặc tả với mọi chi tiết của Metaspace.

Ví dụ, khi `main` gọi `sum(2, 3)`:

1. JVM tạo/ngữ cảnh hóa frame tương ứng với lời gọi `sum` trên ngăn xếp của luồng.
2. Hai tham số `a` và `b` được thao tác qua biến cục bộ và ngăn xếp toán hạng của frame.
3. Lệnh `iadd` tính kết quả; `ireturn` kết thúc lời gọi, trả giá trị về bên gọi.
4. Nếu một phương thức tạo đối tượng bằng `new`, đối tượng thường nằm trên heap; runtime có thể tối ưu hóa cách cấp phát theo những điều kiện cụ thể.

**Garbage collection** giúp thu hồi bộ nhớ heap của đối tượng không còn được truy cập theo cơ chế tương ứng; nó **không thay thế** `close()` đối với tệp, kết nối mạng, khóa hay các tài nguyên cần đóng một cách xác định. Vì vậy ứng dụng vẫn cần `try-with-resources` khi dùng loại tài nguyên phù hợp.

## 7. JVM, môi trường chạy và JDK ở mức tổng quan

Khi nói “cần cài Java để chạy chương trình”, phải xác định **cần công cụ phát triển hay chỉ cần runtime**. Phân biệt ngắn gọn:

| Thành phần | Vai trò trong ví dụ `BytecodeDemo` |
| --- | --- |
| **JVM** | Nạp, kiểm tra và thực thi `BytecodeDemo.class` |
| **Runtime environment / JRE** | JVM cùng các thư viện/module cần thiết để chạy; không nhất thiết kèm trình biên dịch |
| **JDK** | Cung cấp runtime cùng `javac`, `java`, `javap`, `jar` và các công cụ phát triển |

Ở Java hiện đại, ứng dụng có thể được triển khai bằng JDK đầy đủ hoặc **runtime image** thu gọn bằng `jlink`; nhiều vendor không cung cấp một bộ cài JRE riêng như thời Java 8. Sự khác biệt này ảnh hưởng lựa chọn bộ cài và công cụ, **không thay định nghĩa JVM**. Bài kế tiếp tập trung hệ thống hóa các thuật ngữ **ngôn ngữ Java, Java SE, JVM, JDK và môi trường chạy**.

## 8. Tính tương thích và giới hạn quan trọng

**Tương thích phiên bản:** class file có phiên bản định dạng. Ví dụ, biên dịch bằng JDK mới với mức mặc định có thể tạo class không chạy trên Java cũ, dẫn đến lỗi như `UnsupportedClassVersionError`. Khi phải hỗ trợ Java 17 và đang dùng JDK có hỗ trợ mục tiêu này, có thể biên dịch:

```bash
javac --release 17 BytecodeDemo.java
```

Tùy mã nguồn và thư viện sử dụng, tùy chọn `--release 17` giúp đặt mức ngôn ngữ, định dạng class và bề mặt API chuẩn theo Java 17. Nó **không** tự bảo đảm mọi phụ thuộc bên thứ ba hay thư viện native đều chạy được trên môi trường đích; vẫn cần kiểm thử thực tế.

**Tính độc lập nền tảng không bảo đảm hành vi môi trường giống hệt:** hệ điều hành, hệ thống tệp, timezone, locale, quyền truy cập, tài nguyên máy và thư viện native có thể làm kết quả ứng dụng khác nhau.

**Hiệu năng có đánh đổi:** JVM cung cấp khả năng tối ưu động và cơ chế runtime phong phú nhưng thường cần thời gian khởi động, thời gian “warm-up” và bộ nhớ cho chính runtime. Trình thông dịch và JIT có thể phối hợp để cân bằng tốc độ khởi động với hiệu năng lâu dài. Không thể kết luận “Java luôn chậm” hoặc “JIT luôn nhanh hơn mọi cách biên dịch” nếu chưa có workload và phép đo cụ thể.

**Không đánh đồng với mọi cách chạy chương trình Java:** một số công cụ có thể tạo *native executable* bằng biên dịch ahead-of-time. Đó là mô hình triển khai khác so với trường hợp chạy class file trên JVM thông thường; không vì thế mà định nghĩa “JVM là gì” thay đổi.

**Không hiểu nhầm cơ chế bảo vệ:** bytecode verifier kiểm tra nhiều quy tắc cấu trúc và kiểu của class file, nhưng không thể bảo đảm ứng dụng không có lỗ hổng logic, truy cập dữ liệu sai quyền hay lệ thuộc vào thư viện thiếu an toàn.

## 9. Những nhầm lẫn thường gặp

1. **“JVM đọc trực tiếp mã `.java`.”** Trong luồng phổ biến, `javac` tạo `.class` trước; JVM thực thi bytecode. Chế độ chạy nguồn một bước có thể ẩn bước biên dịch.
2. **“Bytecode là mã máy của CPU.”** Bytecode định nghĩa lệnh cho JVM; runtime phải diễn giải hoặc chuyển đổi chúng bằng cơ chế phù hợp của bản triển khai.
3. **“Một class chạy được trên mọi JVM.”** Cần đúng phiên bản class file, API, thư viện và các điều kiện môi trường.
4. **“JVM chỉ là JIT.”** JIT là một kỹ thuật thực thi/tối ưu; JVM còn có nạp lớp, kiểm tra, quản lý runtime, bộ nhớ, ngoại lệ…
5. **“Có GC thì không thể rò rỉ tài nguyên.”** GC không giải phóng mọi tài nguyên bên ngoài heap theo thời điểm ứng dụng cần; các tham chiếu giữ quá lâu cũng có thể gây tình trạng chiếm bộ nhớ không mong muốn.
6. **“JDK và JVM là một.”** JDK bao gồm các công cụ phát triển và runtime; JVM là thành phần thực thi.
7. **“JVM bảo đảm hiệu năng và hành vi đồng nhất trên mọi máy.”** Đặc tả tạo hợp đồng ngữ nghĩa, còn hiệu năng và một số yếu tố môi trường phụ thuộc triển khai/nền tảng.

## 10. Tự kiểm tra kiến thức

**Câu 1.** Vì sao cùng một `BytecodeDemo.class` có thể chạy trên nhiều CPU khác nhau?

Vì class chứa bytecode theo đặc tả JVM; mỗi nền tảng có một bản JVM tương thích chịu trách nhiệm thực thi chúng trên CPU của nền tảng đó. Còn phải đáp ứng phiên bản bytecode và các phụ thuộc của ứng dụng.

**Câu 2.** `javac` và JIT compiler làm cùng một công việc không?

Không. `javac` chuyển mã nguồn Java sang bytecode trước thời điểm chạy; JIT của một số JVM chuyển một phần bytecode sang mã máy khi chương trình đang thực thi, dựa trên chiến lược runtime.

**Câu 3.** Nếu đã có garbage collector, có thể bỏ `try-with-resources` khi đọc tệp không?

Không. Bộ thu gom rác quản lý bộ nhớ đối tượng, trong khi tệp và những tài nguyên hệ điều hành cần được đóng đúng lúc bằng cơ chế như `try-with-resources`.

**Câu 4.** JVM có phải toàn bộ “Java” không?

Không. Java gồm ngôn ngữ, thư viện, công cụ phát triển, chuẩn class file và runtime. JVM là tầng thực thi bytecode ở trung tâm mô hình đó.

## Kết luận

JVM là **máy thực thi trung gian** nằm giữa bytecode Java và nền tảng thật. Trình biên dịch tạo class file theo một hợp đồng chung; JVM tương thích nạp, kiểm tra, thực thi và quản lý các hoạt động runtime trên từng hệ thống. Chính sự tách biệt này tạo nền tảng cho tính di động của Java, đồng thời cho phép tối ưu trong lúc chạy và cung cấp một môi trường thực thi thống nhất. Khi thiết kế hoặc triển khai ứng dụng, luôn xét thêm **tương thích phiên bản, thư viện, môi trường và đo đạc hiệu năng thực tế**.

### Đọc thêm

- [The Java Virtual Machine Specification (Java SE 21)](https://docs.oracle.com/javase/specs/jvms/se21/html/index.html) — mô hình class file, tập lệnh, runtime data areas và vòng đời nạp/liên kết/khởi tạo lớp.
- [Java `javac` documentation (JDK 21)](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html) — công cụ biên dịch Java, trong đó có tùy chọn `--release`.
- [Java `javap` documentation (JDK 21)](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javap.html) — kiểm tra thông tin và bytecode trong tệp class.
