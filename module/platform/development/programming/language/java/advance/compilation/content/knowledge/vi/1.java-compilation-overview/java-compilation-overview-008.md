# Ranh giới giữa đặc tả Java và chi tiết triển khai `javac`

## 1. Vì sao cần phân biệt?

Khi đọc mã Java, ta thường thấy ba câu hỏi khác nhau: **mã có hợp lệ hay không**, **mã hợp lệ phải có ý nghĩa gì**, và **công cụ hiện tại đã dịch nó như thế nào**. Hai câu đầu phần lớn phải trả lời từ đặc tả; câu cuối cần khảo sát một bản triển khai cụ thể, chẳng hạn `javac` của một phiên bản JDK.

Ví dụ, thứ tự đánh giá toán hạng trong biểu thức Java thuộc hợp đồng ngôn ngữ; số lượng lệnh bytecode sinh ra, tên biến tạm do compiler tạo và câu chữ của thông báo lỗi lại không phải một phần của cùng hợp đồng đó. Nhầm hai tầng này dễ dẫn tới kết luận sai khi đổi JDK, chuyển compiler, phân tích hiệu năng, reverse-engineer bytecode hoặc viết công cụ xử lý mã nguồn.

**Mục tiêu bài học:** nhận diện phần được Java bảo đảm, phần do `javac` lựa chọn; dùng đặc tả để giải thích ngữ nghĩa, dùng `javac`/`javap` để kiểm chứng một bản build; không suy diễn quy luật ngôn ngữ từ một lần quan sát bytecode.

## 2. Các tài liệu và tầng trách nhiệm

| Tầng | Điều được quy định hoặc mô tả | Ví dụ | Không nên suy ra |
| --- | --- | --- | --- |
| **JLS — Java Language Specification** | Cú pháp, kiểu, chuyển đổi, overload, definite assignment, kiểm tra lỗi lúc biên dịch, đánh giá biểu thức, ngoại lệ và Java Memory Model | Thứ tự đánh giá đối số từ trái sang phải; trường hợp nào là compile-time error | Compiler nhất thiết có số pha, cấu trúc AST hoặc thông báo chẩn đoán cụ thể |
| **JVMS — Java Virtual Machine Specification** | Cấu trúc `.class`, instruction set, verifier, linking, class initialization và ngữ nghĩa thực thi trên JVM | File lớp hợp lệ, `invokevirtual`, `invokedynamic`, constant pool | Mỗi biểu thức Java phải luôn dịch thành cùng một chuỗi instruction |
| **Java SE/JDK API specifications** | Hợp đồng của thư viện và API công khai | Hành vi `String`, `List`, `javax.tools.JavaCompiler` | Các lớp nội bộ `com.sun.tools.javac.*` là API ổn định |
| **Tài liệu công cụ `javac`** | Các tùy chọn và hành vi được công bố của lệnh compiler trong bản JDK tương ứng | `--release`, `-g`, `-parameters`, `-Xlint` | Mọi lựa chọn tối ưu hóa hoặc pipeline nội bộ đều là cam kết liên phiên bản |
| **Hiện thực `javac` cụ thể** | Cách parser, kiểm tra kiểu, hạ cấp cấu trúc ngôn ngữ và phát mã trong một bản build | Cách biến `for-each` thành instruction; cách tổ chức tên biến tổng hợp | Compiler khác hoặc bản JDK khác buộc phải tạo bytecode giống hệt |
| **JVM thực thi, chẳng hạn HotSpot** | Nạp lớp, interpreter, JIT, quản lý bộ nhớ và tối ưu hóa runtime của một sản phẩm | Có thể inline phương thức lúc chạy | Bytecode do `javac` tạo ra chính là mã máy cuối cùng |

Ranh giới cốt lõi: **JLS quy định ý nghĩa của chương trình Java; JVMS quy định ý nghĩa của class file trên một JVM phù hợp; `javac` là một công cụ biến mã nguồn thành dạng có thể thực thi theo các hợp đồng liên quan.** Hai đặc tả có các mối liên hệ bắt buộc, nhưng không đòi hỏi một chiến lược biên dịch duy nhất.

Không phải mọi thứ cần quan sát trong một ứng dụng đều do JLS định nghĩa: giao tiếp file, network, thời gian, locale, thư viện bên thứ ba và môi trường chạy còn phụ thuộc hợp đồng API và cấu hình thực tế. Ngược lại, việc HotSpot có JIT hay không cũng không đổi quy tắc overload của mã nguồn.

## 3. Một chuỗi biên dịch, nhiều lớp cam kết

```text
Mã .java
  │  ngữ pháp, binding, type checking, flow, ngữ nghĩa nguồn (JLS)
  ▼
Một compiler, ví dụ javac
  │  parse / phân tích / xử lý annotation / chuyển đổi / sinh mã
  │  (cách chia pha và cấu trúc trung gian là chi tiết implementation)
  ▼
File .class
  │  định dạng và tính hợp lệ theo JVMS
  ▼
JVM: load → link/verify → initialize khi cần → execute
  │  interpreter/JIT/GC là lựa chọn hiện thực trong giới hạn hợp đồng
  ▼
Hành vi quan sát được theo đặc tả và môi trường
```

Các tên pha như parse, enter, attribution, flow, desugar và generate thường hữu ích khi nghiên cứu kiến trúc `javac`. Tuy nhiên, **không dùng những tên pha đó như quy tắc bắt buộc của ngôn ngữ Java**. Một compiler phù hợp có thể tổ chức hoặc kết hợp các bước khác nhau.

Tương tự, thấy một cấu trúc nguồn được "desugar" thành vòng lặp, iterator hay một phương thức helper chỉ mô tả cách compiler thực hiện. Hợp đồng ở phía người lập trình là quy tắc đánh giá và hành vi quan sát được mà JLS quy định.

## 4. Điều gì là quy tắc ngôn ngữ, điều gì là lựa chọn compiler?

### 4.1. Kiểm tra kiểu và lỗi bắt buộc

Xét đoạn không hợp lệ:

```java
class WrongType {
    int count = "three";
}
```

Gán `String` cho `int` ở đây không có phép chuyển đổi hợp lệ, nên **phải bị phát hiện là lỗi lúc biên dịch**. Đó là kết luận ở cấp JLS. Nhưng văn bản cụ thể như "incompatible types", vị trí dấu mũ, mã lỗi, gợi ý sửa, ngôn ngữ thông báo hoặc số lượng lỗi được in ra là hành vi chẩn đoán của công cụ. `javac` cũng có thể thay đổi thông điệp giữa các bản phát hành.

**Cách kiểm chứng:** đối chiếu quy tắc chuyển đổi gán trong JLS trước; sau đó chạy `javac` nếu cần một bản log để hỗ trợ sửa mã. Không sử dụng câu chữ thông báo lỗi làm đặc tả về ngữ nghĩa Java.

### 4.2. Thứ tự thực thi có thể quan sát

Lưu thành `EvaluationOrder.java`:

```java
public class EvaluationOrder {
    static int next(String label, int value) {
        System.out.println(label);
        return value;
    }

    static int sum(int a, int b) {
        return a + b;
    }

    public static void main(String[] args) {
        int result = sum(next("left", 2), next("right", 3));
        System.out.println(result);
    }
}
```

Biên dịch và chạy với JDK 17+:

```bash
javac EvaluationOrder.java
java EvaluationOrder
```

Đầu ra xác định:

```text
left
right
5
```

Java đánh giá các đối số của lời gọi từ trái qua phải (JLS `15.7.4); một compiler phù hợp không thể đổi kết quả thành `right` trước `left` chỉ vì cách đó dễ tối ưu hơn. Tuy nhiên, cách bảo toàn thứ tự bằng stack JVM, biến tạm hay tối ưu hóa cụ thể có thể khác. Đây là cách phân biệt **ngữ nghĩa quan sát được** và **cơ chế tạo mã**.

### 4.3. Mã bytecode không có một hình dạng duy nhất

```java
public class BytecodeExample {
    public static int calculate(int input) {
        int plusOne = input + 1;
        return plusOne * 2;
    }

    public static void main(String[] args) {
        System.out.println(calculate(4));
    }
}
```

```bash
javac BytecodeExample.java
java BytecodeExample
javap -c -p BytecodeExample
```

Kết quả chạy `java`:

```text
10
```

`javap -c` cho biết các instruction **thực tế được sinh bởi bộ công cụ đang dùng**; đây là bằng chứng rất tốt để nghiên cứu class file. Nhưng không nên viết quy tắc như "Java bắt buộc dùng `iadd` rồi `imul` cho phương thức này" chỉ vì một lần quan sát. Khi thay đổi compiler, cờ build hoặc phiên bản JDK, biểu diễn có thể thay đổi trong khi nghĩa của phương thức được bảo toàn.

Một số compiler có thể tính trước hằng, thay đổi thứ tự lệnh khi an toàn, gộp hoặc bỏ biến trung gian. Chỉ các biến đổi vẫn giữ hợp đồng liên quan mới được phép; tối ưu hóa không phải giấy phép làm sai quy tắc đánh giá, ngoại lệ hay Java Memory Model.

### 4.4. Hạ cấp cú pháp không phải cú pháp gốc

Vòng lặp enhanced `for` có quy tắc riêng trong JLS. Với array và `Iterable`, compiler có thể biến cấu trúc này thành những thao tác mức thấp khác nhau. Khi học, trước hết hỏi: biểu thức lấy nguồn được đánh giá mấy lần, thứ tự lặp ra sao, kiểu và chuyển đổi của biến lặp là gì? Sau đó dùng `javap` để xem `javac` đã chọn chuỗi instruction nào.

Các tính năng như lambda, method reference, record và chuỗi nối bằng `+` càng minh họa rõ điều này: một bản `javac` có thể dùng `invokedynamic`, bootstrap method hoặc phương thức tổng hợp. Đó là chi tiết cần chú ý khi đọc bytecode, nhưng không nên gắn hình dạng cụ thể của nó thành bảo đảm vĩnh viễn của cú pháp Java.

## 5. Compile-time semantics khác với tối ưu hóa tùy chọn

Không phải mọi phép tính xuất hiện trong class file dưới dạng hằng đều là "compiler tự tối ưu". JLS có khái niệm **constant expression** và **constant variable** với hệ quả ngôn ngữ, chẳng hạn một số phép tính hằng có thể dùng trong nhãn `case` và một số giá trị hằng của trường có thể được chèn trực tiếp tại chỗ sử dụng.

Ví dụ:

```java
public class CompileTimeConstants {
    static final int BASE = 20;
    static final int DOUBLE = BASE * 2;

    public static void main(String[] args) {
        int value = 40;
        switch (value) {
            case DOUBLE -> System.out.println("match");
            default -> System.out.println("no match");
        }
    }
}
```

```bash
javac CompileTimeConstants.java
java CompileTimeConstants
```

```text
match
```

`DOUBLE` là constant variable, và `case DOUBLE` là nhãn hằng hợp lệ theo quy tắc của ngôn ngữ. Còn việc một biểu thức thông thường được tối ưu sang instruction nào có thể phụ thuộc compiler. Khi thay đổi một trường `public static final` là compile-time constant trong một thư viện, **client đã biên dịch trước có thể vẫn chứa giá trị cũ**; cần biên dịch lại client để cập nhật giá trị đã chèn vào binary. Không nhầm vấn đề binary compatibility này với lỗi cache của `javac`.

## 6. Phiên bản Java: ngôn ngữ, API và class file là ba trục khác nhau

Một nhầm lẫn phổ biến: "đã phát ra bytecode cho Java cũ thì chắc chắn chạy được trên Java cũ". Chỉ kiểm soát phiên bản class file là chưa đủ nếu mã vẫn tham chiếu API chưa tồn tại ở runtime đích.

| Tùy chọn `javac` | Tác động chính | Giới hạn |
| --- | --- | --- |
| `--source N` | Quy tắc cú pháp/ngôn ngữ chấp nhận ở mức Java N | Không tự khóa tập API theo Java N |
| `--target N` | Phiên bản class file sinh ra | Không tự bảo đảm mọi API được gọi tồn tại trên runtime Java N |
| `--release N` | Ràng buộc ngôn ngữ, định dạng class file và API nền tảng của Java N | Không xác nhận tương thích của mọi dependency ngoài nền tảng hoặc điều kiện runtime |
| Không ghi các cờ trên | Dùng mặc định của bản `javac` đang chạy | Mặc định có thể đổi theo JDK |

Ví dụ tạo `ModernApi.java`:

```java
public class ModernApi {
    public static void main(String[] args) {
        System.out.println("ab".repeat(2));
    }
}
```

Với một JDK 17+ có hỗ trợ `--release 8`:

```bash
javac --release 17 ModernApi.java
java ModernApi
javac --release 8 ModernApi.java
```

Lệnh chạy sau lần biên dịch đầu in:

```text
abab
```

Lệnh `javac --release 8` phải **thất bại** vì `String.repeat(int)` được đưa vào Java 11, không có trong API nền tảng Java 8. Không cam kết nguyên văn nội dung chẩn đoán. Thử nghiệm này chứng tỏ lỗi liên quan tới **hợp đồng API theo release**, không phải riêng cú pháp hay version header của file `.class`.

Khi triển khai thực tế, dùng `--release` phù hợp target, xác định rõ phiên bản JDK build/run, kiểm tra thư viện ngoài, module, tính năng preview, phụ thuộc hệ điều hành và chạy test trên runtime đích. Không kết luận tương thích chỉ từ việc build thành công.

## 7. Các tùy chọn làm thay đổi artifact mà không đổi ý nghĩa nguồn

- `-g` hoặc `-g:lines,vars,source` yêu cầu thông tin debug bổ sung trong class file; có thể quan sát bằng `javap -l` hoặc `-v`. Thiếu thông tin này không làm các biến cục bộ trong mã nguồn mất đi về mặt ngữ nghĩa.
- `-parameters` ghi metadata tên tham số của phương thức/constructor để reflection qua `java.lang.reflect.Parameter` có thể truy xuất tên được khai báo. Đây là đặc tính của artifact đã build, không chứng minh quy tắc tên tham số trong mã nguồn thay đổi.
- `-Xlint` bật các cảnh báo của `javac`; `-Werror` khiến một cảnh báo trở thành điều kiện build thất bại. Cảnh báo là công cụ kiểm soát chất lượng, không tự trở thành quy tắc cấm của JLS.
- `-encoding` kiểm soát cách `javac` giải mã file nguồn; sự khác nhau về encoding có thể làm đầu vào compiler khác nhau. Ghi rõ UTF-8 trong build nếu cần tính tái lập.
- `-classpath`/`--class-path` và `--module-path` thay đổi môi trường tìm kiểu/phụ thuộc trong lúc biên dịch. Không nhầm với classpath/module path thực thi của lệnh `java`.
- `-d` thay đổi thư mục output, không thay đổi ngữ nghĩa Java của chương trình.

Trong một pipeline CI, ghi lại phiên bản công cụ (`javac -version`), tùy chọn compiler, annotation processors, dependency resolution và nguồn sinh mã. Hai class file khác byte-for-byte không tự chứng minh một bản build sai; hãy tìm khác biệt có ý nghĩa ở hành vi, ABI, metadata, hoặc các ràng buộc tái lập đã đặt ra.

## 8. Annotation processing và API compiler

`javac` có khả năng chạy **annotation processors** trong lúc biên dịch; processor có thể phát sinh mã nguồn, tài nguyên hoặc thông báo chẩn đoán theo API chuẩn. Điều đó không làm một annotation bất kỳ tự có nghĩa "sinh mã"; cần kiểm tra processor nào có mặt, được cấu hình thế nào, có được thực thi trong bản JDK và build system đang dùng không.

`javax.annotation.processing` và `javax.tools` là các API công khai có tài liệu cho xử lý annotation và tích hợp trình biên dịch. Ví dụ công cụ có thể dùng `ToolProvider.getSystemJavaCompiler()` để lấy compiler hệ thống khi chạy trên một JDK cung cấp compiler; kết quả có thể là `null` nếu môi trường không cung cấp compiler tương ứng. Ngược lại, các gói nội bộ bắt đầu bằng `com.sun.tools.javac` có thể hữu ích cho nghiên cứu/compiler plugin nhưng **không phải API ổn định chỉ vì chúng có trong một JDK**. Khi phụ thuộc nội bộ, phải xét độ tương thích theo đúng phiên bản và chính sách đóng gói module.

Đừng coi các class được processor sinh ra là cú pháp ngôn ngữ Java mới. Phân tách rõ: nguồn người viết, nguồn được sinh, plugin/processor và các cam kết của compiler.

## 9. Khi đọc `javap`, decompiler và stack trace

`javap` phân tích class file; decompiler cố tái dựng mã nguồn; stack trace và debugger dùng thông tin class file cùng metadata có sẵn. Không công cụ nào trong ba loại này thay thế được JLS khi cần giải thích ngữ nghĩa nguồn.

Ví dụ thấy `lambda$main$0` hay biến tổng hợp trong một bản output không có nghĩa lập trình viên đã định nghĩa chúng trong mã nguồn. Tương tự, không thấy biến local ở `javap -c` không có nghĩa biến đó không tồn tại ở mức khái niệm ngôn ngữ. Biểu diễn JVM thiên về stack, slots và instruction; biến, khối lệnh và biểu thức trong nguồn có thể không ánh xạ 1–1.

Khi điều tra một vấn đề:
1. **Xác định câu hỏi:** tính hợp lệ của source, khác biệt artifact, hành vi runtime hay hiệu năng.
2. **Chọn tài liệu:** JLS cho cú pháp/ngữ nghĩa; JVMS cho file class/instruction; API docs cho thư viện; manual `javac` cho cờ; tài liệu HotSpot/JVM nếu xét JIT/GC.
3. **Tạo bản repro nhỏ**, ghi JDK/toolchain/cờ; nếu là lỗi runtime, ghi runtime thực tế.
4. **So sánh hành vi có thể quan sát** trước, sau đó dùng `javap`/log như bằng chứng phụ trợ.
5. **Không khái quát hóa từ một output:** một chi tiết implementation chỉ được coi là hợp đồng khi có tài liệu tương ứng.

## 10. Những ngộ nhận thường gặp

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| "`javac` tạo bytecode kiểu này, vậy JLS bắt buộc như vậy." | JLS ràng buộc ngữ nghĩa; bytecode còn tùy compiler và JVMS. |
| "Cùng Java source phải tạo file `.class` byte-identical trên mọi JDK." | Không có bảo đảm chung như vậy. Có thể so sánh mức ABI/behavior hoặc đặt tiêu chí reproducible build riêng. |
| "Thông báo lỗi của `javac` là nguyên văn luật Java." | Luật compile-time error nằm trong JLS; thông báo, vị trí và gợi ý có thể khác. |
| "`--target 8` đồng nghĩa không thể dùng API mới hơn Java 8." | Cần kiểm soát API bằng `--release 8` hoặc quy trình tương đương. |
| "JIT tối ưu một phương thức nghĩa là `javac` đã sinh machine code tối ưu đó." | `javac` thường phát class file; JIT ở runtime là tầng khác. |
| "Mã nguồn không có helper method nên class file cũng không thể có." | Compiler có thể sinh phương thức/lớp tổng hợp phù hợp với hợp đồng. |
| "Chỉ cần thử trên máy mình để biết mọi JVM đều hành xử vậy." | Một thử nghiệm cung cấp bằng chứng cho toolchain/môi trường đó; muốn kết luận chung phải viện dẫn đặc tả. |

Đối với lỗi cạnh tranh dữ liệu, ranh giới còn quan trọng hơn: JLS `17 (Java Memory Model) xác định những hành vi bộ nhớ hợp lệ; trình biên dịch/JIT/CPU được tối ưu trong phạm vi đó. Một lần chạy "có vẻ đúng" không chứng minh chương trình thiếu đồng bộ đã an toàn.

## 11. Bài tập tự kiểm tra và đáp án

**Bài 1.** Một bản `javac` sinh `invokedynamic` cho phép nối chuỗi, bản khác dùng chuỗi lời gọi khác. Hai bản có tự động vi phạm Java không?

**Đáp án:** Không. Kiểm tra xem chúng có bảo toàn ngữ nghĩa nối chuỗi và các ràng buộc liên quan không; `invokedynamic` chỉ là một cách hiện thực ở tầng class file.

**Bài 2.** Chạy `javac --target 8` thành công, nhưng khi chạy Java 8 gặp `NoSuchMethodError` do gọi API chỉ có ở Java 11. Sai sót ở đâu?

**Đáp án:** Mức target của class file chưa khóa API nền tảng. Dùng `--release 8` với toolchain hỗ trợ và kiểm tra dependency/runtime đích.

**Bài 3.** Một unit test khẳng định "javac luôn tạo đúng ba instruction cho biểu thức `x + 1`". Đây là test quy tắc ngôn ngữ hay test implementation?

**Đáp án:** Test implementation. Nên cố định bản JDK/compiler và mục đích kiểm thử khi cần regression ở mức bytecode; không dùng nó để chứng minh JLS.

**Bài 4.** Muốn biết toán hạng nào được đánh giá trước trong lời gọi phương thức có side effect, tra ở đâu?

**Đáp án:** JLS `15.7 và `15.12, nhất là `15.7.4` về thứ tự đánh giá danh sách đối số; thử nghiệm `EvaluationOrder` chỉ minh họa quy tắc.

## 12. Tài liệu chuẩn nên tra

- **Java Language Specification (JLS), Java SE 21:** https://docs.oracle.com/javase/specs/jls/se21/html/ — đặc biệt chương 5 (conversions), 15 (expressions), 17 (memory model).
- **Java Virtual Machine Specification (JVMS), Java SE 21:** https://docs.oracle.com/javase/specs/jvms/se21/html/ — `class` format, verification, instruction set, execution.
- **JDK 21 `javac` tool reference:** https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html — ý nghĩa tùy chọn, môi trường compile, annotation processing.
- **Java SE 21 API reference:** https://docs.oracle.com/en/java/javase/21/docs/api/ — hợp đồng thư viện công khai.

Các liên kết gắn với **Java 21** để có một mốc học tập nhất quán; khi làm dự án dùng Java release khác, phải mở đúng phiên bản đặc tả và tài liệu công cụ tương ứng.