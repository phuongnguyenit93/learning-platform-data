# Stream Gatherers và Class-File API: từ preview trong Java 22 đến chính thức từ JDK 24

Java 22 giới thiệu hai API preview hướng tới những công việc khác nhau nhưng đều quan trọng với hệ sinh thái Java:

- **Stream Gatherers** mở rộng Stream API bằng cách cho phép định nghĩa các intermediate operation tùy chỉnh, có thể giữ trạng thái, gom nhóm, phát ra nhiều kết quả hoặc dừng xử lý sớm.
- **Class-File API** cung cấp API chuẩn để đọc, tạo và biến đổi file `.class`, tức cấu trúc bytecode mà JVM sử dụng.

Cả hai trải qua hai vòng preview ở JDK 22 và JDK 23, sau đó trở thành API chính thức từ JDK 24. Bài học tập trung vào cách dùng ổn định từ JDK 24 trở lên; mã preview chỉ xuất hiện trong phần lịch sử để giải thích quá trình phát triển.

## Lộ trình từ preview đến API chính thức

| Tính năng | JDK 22 | JDK 23 | JDK 24 trở đi |
|---|---|---|---|
| Stream Gatherers | [JEP 461](https://openjdk.org/jeps/461) — Preview | [JEP 473](https://openjdk.org/jeps/473) — Second Preview | [JEP 485](https://openjdk.org/jeps/485) — Final |
| Class-File API | [JEP 457](https://openjdk.org/jeps/457) — Preview | [JEP 466](https://openjdk.org/jeps/466) — Second Preview | [JEP 484](https://openjdk.org/jeps/484) — Final |

Trong các bản preview, tên, chữ ký phương thức và một số chi tiết API có thể thay đổi. Vì vậy, khi đọc tài liệu cũ hoặc nâng cấp mã thử nghiệm từ JDK 22/23, hãy đối chiếu với API final thay vì mặc định mã preview vẫn tương thích. Với JDK 24 trở lên, hai tính năng này không cần bật `--enable-preview`.

---

## Phần I — Stream Gatherers

### Vì sao Stream API cần Gatherer?

Stream API có sẵn nhiều intermediate operation quen thuộc như `map`, `filter`, `flatMap`, `distinct`, `sorted` và `limit`. Các thao tác này đáp ứng phần lớn nhu cầu biến đổi dữ liệu, nhưng đôi khi một bài toán cần xử lý nhiều phần tử cùng lúc hoặc phải lưu trạng thái giữa các phần tử.

Ví dụ:

- Chia danh sách sự kiện thành từng nhóm ba sự kiện.
- Tạo các cửa sổ trượt để tính trung bình động.
- Phát ra tổng tích lũy sau mỗi phần tử.
- Loại bỏ các phần tử trùng nhau đứng cạnh nhau.
- Xử lý một số tác vụ I/O đồng thời với giới hạn số tác vụ đang chạy.

Trước Gatherers, những bài toán này thường cần vòng lặp riêng, một `Spliterator`, hoặc một cấu trúc trung gian khác. **Gatherer** bổ sung một điểm mở rộng cho Stream API: người lập trình có thể mô tả một intermediate operation mới và tiếp tục kết hợp nó với các operation khác trong pipeline.

### Gatherer hoạt động như thế nào?

Một Gatherer nhận các phần tử kiểu `T` từ stream đầu vào và có thể phát ra không, một hoặc nhiều phần tử kiểu `R` xuống operation tiếp theo. Nó có thể không giữ trạng thái hoặc sử dụng một trạng thái trung gian để ghi nhớ dữ liệu đã nhận.

```text
Stream<T>
   |
   v
Gatherer<T, A, R>
   |  nhận từng T
   |  cập nhật trạng thái A
   |  phát ra 0..n phần tử R
   v
Stream<R>
   |
   v
Các intermediate operation tiếp theo / terminal operation
```

Trong đó:

- `T`: kiểu phần tử đầu vào.
- `A`: kiểu trạng thái trung gian, có thể là một cấu trúc mutable.
- `R`: kiểu phần tử đầu ra.

`Stream.gather(Gatherer)` là một **stateful intermediate operation**. Pipeline vẫn được đánh giá theo cơ chế lazy thông thường: Gatherer chỉ thực sự xử lý dữ liệu khi terminal operation được thực thi.

Một Gatherer có thể được mô tả bằng bốn thành phần:

| Thành phần | Vai trò |
|---|---|
| `initializer` | Tạo trạng thái ban đầu cho một lần thực thi hoặc một phân vùng xử lý. |
| `integrator` | Nhận trạng thái, phần tử kế tiếp và `Downstream`; cập nhật trạng thái hoặc phát kết quả. |
| `combiner` | Kết hợp hai trạng thái khi Gatherer hỗ trợ xử lý song song. |
| `finisher` | Thực hiện thao tác cuối khi upstream đã hết dữ liệu, có thể phát thêm kết quả. |

Không phải Gatherer nào cũng cần đủ bốn thành phần. API cung cấp các factory method cho Gatherer không trạng thái, Gatherer chạy tuần tự và Gatherer có khả năng kết hợp trạng thái để xử lý song song.

### Các Gatherer có sẵn trong JDK

Lớp `java.util.stream.Gatherers` cung cấp một số Gatherer phổ biến. Các phương thức sau thuộc API ổn định từ JDK 24 và vẫn có trong Java SE 27:

| Phương thức | Cách hoạt động | Tình huống phù hợp |
|---|---|---|
| `windowFixed(size)` | Chia phần tử thành các nhóm liên tiếp, không chồng lấp. Nhóm cuối có thể ít phần tử hơn `size`. | Gom sự kiện theo lô, chia dữ liệu thành batch. |
| `windowSliding(size)` | Tạo cửa sổ trượt; cửa sổ kế tiếp bỏ phần tử cũ nhất và nhận thêm phần tử mới. | Trung bình động, phân tích chuỗi thời gian. |
| `scan(initial, accumulator)` | Phát ra kết quả tích lũy sau mỗi phần tử. | Tổng tích lũy, trạng thái tiến trình. |
| `fold(initial, accumulator)` | Tích lũy toàn bộ đầu vào theo thứ tự và phát ra một kết quả cuối. | Tạo một giá trị tổng hợp khi không có phép kết hợp song song phù hợp. |
| `mapConcurrent(maxConcurrency, mapper)` | Ánh xạ phần tử bằng các tác vụ chạy đồng thời, giới hạn số tác vụ và sử dụng virtual thread. | Gọi dịch vụ hoặc thực hiện tác vụ I/O độc lập có giới hạn đồng thời. |

Các cửa sổ được tạo bởi `windowFixed` và `windowSliding` là `List` không thể sửa đổi. Với `windowFixed`, cửa sổ cuối có thể là cửa sổ thiếu. Với `windowSliding`, nếu stream có ít phần tử hơn kích thước cửa sổ thì Gatherer tạo một cửa sổ chứa toàn bộ phần tử hiện có.

#### Chia dữ liệu thành các batch cố định

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

public class FixedWindowsExample {
    public static void main(String[] args) {
        List<List<Integer>> batches = Stream.of(1, 2, 3, 4, 5, 6, 7, 8)
                .gather(Gatherers.windowFixed(3))
                .toList();

        batches.forEach(System.out::println);
    }
}
```

Kết quả:

```text
[1, 2, 3]
[4, 5, 6]
[7, 8]
```

Phần tử `7` và `8` vẫn được giữ lại trong cửa sổ cuối. Nếu cần mỗi batch có đủ ba phần tử, chương trình phải tự quyết định cách xử lý batch cuối, chẳng hạn bỏ nó hoặc bổ sung dữ liệu.

#### Tạo cửa sổ trượt

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

public class SlidingWindowExample {
    public static void main(String[] args) {
        List<List<Integer>> windows = Stream.of(10, 20, 30, 40, 50)
                .gather(Gatherers.windowSliding(3))
                .toList();

        windows.forEach(System.out::println);
    }
}
```

Kết quả:

```text
[10, 20, 30]
[20, 30, 40]
[30, 40, 50]
```

Đây là cách thuận tiện để tạo các nhóm phần tử liên tiếp có phần giao nhau. Nếu dùng để tính toán trên dữ liệu lớn, cần cân nhắc kích thước cửa sổ vì mỗi cửa sổ chứa một danh sách phần tử.

#### Tính giá trị tích lũy bằng `scan` và `fold`

`scan` phát ra trạng thái sau từng phần tử:

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

public class ScanExample {
    public static void main(String[] args) {
        List<Integer> runningTotals = Stream.of(2, 3, 5, 7)
                .gather(Gatherers.scan(() -> 0, Integer::sum))
                .toList();

        System.out.println(runningTotals);
    }
}
```

Kết quả là `[2, 5, 10, 17]`. Giá trị khởi tạo `0` được dùng làm trạng thái ban đầu; kết quả đầu tiên được phát ra sau khi xử lý phần tử đầu vào đầu tiên.

`fold` chỉ phát ra kết quả tổng hợp cuối cùng:

```java
import java.util.Optional;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

public class FoldExample {
    public static void main(String[] args) {
        Optional<Integer> total = Stream.of(2, 3, 5, 7)
                .gather(Gatherers.fold(() -> 0, Integer::sum))
                .findFirst();

        System.out.println(total.orElse(0));
    }
}
```

Kết quả là `17`. Với stream rỗng, `fold` vẫn có thể phát ra giá trị ban đầu do `Supplier` cung cấp. `fold` phù hợp với phép tích lũy có thứ tự hoặc không có combiner hợp lệ; nếu phép toán có thể biểu diễn bằng `reduce` hoặc `collect` một cách tự nhiên, hãy cân nhắc dùng operation đó trước.

#### Ánh xạ tác vụ đồng thời bằng `mapConcurrent`

`mapConcurrent` chạy mapper trên các virtual thread với giới hạn đồng thời do chương trình cung cấp. Kết quả vẫn giữ encounter order của stream:

```java
import java.util.List;
import java.util.stream.Gatherers;

public class ConcurrentMappingExample {
    record Product(String id) {}
    record Price(String productId, int amount) {}

    static Price fetchPrice(Product product) {
        // Thay bằng lời gọi dịch vụ thực tế.
        return new Price(product.id(), 100);
    }

    public static void main(String[] args) {
        List<Product> products = List.of(
                new Product("P-01"),
                new Product("P-02"),
                new Product("P-03")
        );

        List<Price> prices = products.stream()
                .gather(Gatherers.mapConcurrent(8, ConcurrentMappingExample::fetchPrice))
                .toList();

        prices.forEach(System.out::println);
    }
}
```

Trong ví dụ, tối đa tám mapper được thực thi đồng thời. Giá trị này là giới hạn, không phải cam kết rằng luôn có tám tác vụ chạy cùng lúc.

`mapConcurrent` hữu ích với tác vụ chờ I/O có thời gian chờ đáng kể. Nó không tự làm cho phép tính CPU-bound chạy nhanh hơn; với tác vụ tính toán nặng, cần đo hiệu năng và chọn mô hình song song phù hợp. Khi downstream không cần thêm dữ liệu, việc hủy các tác vụ đang chạy chỉ được cố gắng theo cơ chế best-effort.

### Tự tạo Gatherer

Khi các operation có sẵn chưa đáp ứng yêu cầu, có thể triển khai `Gatherer` riêng. Ví dụ sau chỉ phát ra mỗi phần tử thứ ba:

```java
import java.util.List;
import java.util.stream.Gatherer;
import java.util.stream.Stream;

public class EveryThirdElementExample {
    public static void main(String[] args) {
        Gatherer<Integer, int[], Integer> everyThird = Gatherer.ofSequential(
                () -> new int[1],
                (count, element, downstream) -> {
                    count[0]++;

                    if (count[0] % 3 == 0) {
                        return downstream.push(element);
                    }

                    return true;
                }
        );

        List<Integer> result = Stream.of(10, 20, 30, 40, 50, 60, 70, 80, 90)
                .gather(everyThird)
                .toList();

        System.out.println(result);
    }
}
```

Kết quả là `[30, 60, 90]`.

Trong ví dụ:

- `int[]` là trạng thái `A`; `initializer` tạo một trạng thái mới cho lần thực thi.
- `integrator` nhận phần tử hiện tại, cập nhật bộ đếm và quyết định có phát phần tử xuống `downstream` hay không.
- `downstream.push(element)` trả về `false` khi downstream không muốn nhận thêm dữ liệu. Trả về giá trị này giúp Gatherer dừng nhận đầu vào khi pipeline phía sau đã kết thúc sớm.
- `ofSequential` khai báo rõ Gatherer này xử lý tuần tự. Nó không cung cấp `combiner` để ghép trạng thái của các phân vùng song song.

Với Gatherer cần chạy song song, phải thiết kế `combiner` sao cho hai trạng thái độc lập có thể ghép lại mà vẫn cho kết quả đúng theo ngữ nghĩa của operation. Không nên thêm combiner chỉ để bật parallel nếu chưa chứng minh được tính đúng đắn của phép ghép.

### Khi nào Gatherer có thể chạy song song?

Gatherer chỉ có thể được xử lý song song khi có combiner phù hợp. Khi stream được chia thành các phân vùng, mỗi phân vùng có trạng thái riêng; sau khi tích hợp các phần tử, combiner ghép các trạng thái để tạo trạng thái cuối. Cách tổ chức này giúp Gatherer tránh phải chia sẻ một trạng thái mutable duy nhất giữa nhiều thread.

Một số điểm cần chú ý:

- `Gatherer.ofSequential(...)` chỉ mô tả operation tuần tự.
- `Gatherer.of(...)` với `initializer`, `integrator`, `combiner` và `finisher` tạo Gatherer có khả năng xử lý song song.
- `Gatherer.of(integrator)` dùng cho operation không trạng thái.
- Integrator trả về `false` để báo rằng nó không muốn nhận thêm phần tử.
- `finisher` được gọi khi upstream kết thúc và có thể phát ra kết quả còn nằm trong trạng thái.
- `andThen` cho phép nối đầu ra của Gatherer này với đầu vào của Gatherer khác.

Không nên nhầm khả năng chạy song song của Gatherer với việc mapper tự chạy đồng thời. `mapConcurrent` là một operation dựng sẵn có cơ chế chạy tác vụ đồng thời riêng; Gatherer tùy chỉnh cần combiner đúng mới có thể tận dụng parallel stream.

### Gatherer khác Collector ở đâu?

| Tiêu chí | Gatherer | Collector |
|---|---|---|
| Vị trí trong pipeline | Intermediate operation qua `Stream.gather(...)`. | Terminal reduction qua `collect(...)`. |
| Đầu ra | Có thể phát ra nhiều phần tử và tiếp tục pipeline. | Tạo một kết quả cuối từ toàn bộ phần tử. |
| Trạng thái | Có thể lưu trạng thái giữa các lần tích hợp. | Dùng container tích lũy trong quá trình collect. |
| Trường hợp dùng | Biến đổi cấu trúc luồng, cửa sổ, phát kết quả tăng dần, dừng sớm. | Gom dữ liệu thành `List`, `Map`, nhóm hoặc kết quả tổng hợp. |

Ví dụ, nếu chỉ cần gom các phần tử thành `List`, `Collectors.toList()` hoặc `Stream.toList()` phù hợp hơn. Nếu cần chia dữ liệu thành từng cửa sổ rồi tiếp tục `map` hoặc `filter` trên từng cửa sổ, Gatherer thể hiện đúng vị trí của thao tác đó trong pipeline.

---

## Phần II — Class-File API

### Class file là gì?

Sau khi mã Java được biên dịch, trình biên dịch tạo ra file `.class`. File này lưu biểu diễn mà JVM hiểu, bao gồm:

- Thông tin class, superclass và interface.
- Field, method và access flag.
- Constant pool với tên kiểu, tên method, chuỗi và các hằng số được tham chiếu.
- Bytecode của method.
- Attribute như annotation, generic signature, debug information và thông tin bootstrap.

Các framework, agent, công cụ phân tích bytecode, bộ instrument và công cụ tạo mã có thể cần đọc hoặc thay đổi cấu trúc này. Trước Class-File API, nhà phát triển thường dựa vào thư viện bên ngoài hoặc API nội bộ của JDK. JDK 24 đưa vào một API chuẩn để xử lý class file trực tiếp.

Class-File API thao tác với **bytecode đã biên dịch**, không phải API để phân tích cú pháp mã nguồn Java. Nếu mục tiêu là phân tích source code, cần dùng Java Compiler API hoặc công cụ phân tích cú pháp phù hợp.

### Từ JEP 457 đến JEP 484

| Phiên bản | JEP | Trạng thái |
|---|---|---|
| JDK 22 | [JEP 457](https://openjdk.org/jeps/457) | Class-File API lần đầu xuất hiện dưới dạng preview. |
| JDK 23 | [JEP 466](https://openjdk.org/jeps/466) | Preview lần thứ hai, tiếp tục điều chỉnh mô hình và API. |
| JDK 24 | [JEP 484](https://openjdk.org/jeps/484) | API được hoàn thiện và trở thành một phần chính thức của Java SE. |

Package chính là `java.lang.classfile`. Các package liên quan gồm `java.lang.classfile.attribute`, `java.lang.classfile.constantpool` và `java.lang.classfile.instruction`. Từ JDK 24 trở lên, có thể sử dụng API này mà không bật preview.

### Mô hình chính: Model, Element, Builder và Transform

Class-File API tổ chức cấu trúc class file theo các mô hình bất biến:

| Thành phần | Vai trò |
|---|---|
| `ClassFile` | Context cung cấp các thao tác parse, build, transform và verify cùng các tùy chọn xử lý. |
| `ClassModel`, `MethodModel`, `FieldModel`, `CodeModel` | Mô hình đọc class, method, field và phần bytecode. |
| `ClassElement`, `MethodElement`, `CodeElement` | Các element xuất hiện khi duyệt cấu trúc tương ứng. Một model cũng có thể là element của model cha. |
| `ClassBuilder`, `MethodBuilder`, `CodeBuilder` | Xây dựng class file, method và bytecode. |
| `ClassTransform`, `MethodTransform`, `CodeTransform` | Mô tả cách giữ lại, bỏ hoặc thay thế element khi biến đổi. |
| `ClassDesc`, `MethodTypeDesc` | Biểu diễn tên class và method descriptor theo dạng symbolic, giảm việc thao tác với chuỗi descriptor thô. |

Model và element là immutable, có thể được duyệt theo cấu trúc cây hoặc qua chuỗi element. Việc parse được thực hiện lazy: dữ liệu chi tiết chỉ được đọc khi accessor hoặc thao tác duyệt cần đến nó. Vì vậy, một lỗi cấu trúc có thể được phát hiện ở thời điểm truy cập một phần model, không nhất thiết ngay tại lời gọi `parse`. Tài liệu API cũng lưu ý model lazy có thể không thread-safe; tránh chia sẻ một model cho nhiều thread nếu chưa có bảo đảm phù hợp.

### Đọc và phân tích file `.class`

`ClassFile.of()` tạo context với tùy chọn mặc định. Có thể parse từ `byte[]` hoặc từ `Path`:

```java
import java.io.IOException;
import java.lang.classfile.ClassFile;
import java.lang.classfile.ClassModel;
import java.lang.classfile.FieldModel;
import java.lang.classfile.MethodModel;
import java.nio.file.Path;

public class InspectClassFile {
    public static void main(String[] args) throws IOException {
        ClassFile classFile = ClassFile.of();
        ClassModel model = classFile.parse(Path.of(args[0]));

        System.out.println("Fields:");
        for (FieldModel field : model.fields()) {
            System.out.println("- " + field.fieldName().stringValue());
        }

        System.out.println("Methods:");
        for (MethodModel method : model.methods()) {
            System.out.println("- " + method.methodName().stringValue());
        }
    }
}
```

Chạy chương trình với đường dẫn tới file `.class` cần kiểm tra. `ClassModel` cung cấp các accessor như `fields()`, `methods()`, `flags()` và `thisClass()`. Từ `MethodModel`, có thể đi sâu vào `CodeModel` rồi duyệt từng `CodeElement` để phân tích instruction.

Ví dụ, một công cụ phân tích dependency có thể duyệt các `InvokeInstruction` và `FieldInstruction` để tìm class mà bytecode tham chiếu. Cách duyệt này không cần tải class đó vào JVM bằng class loader.

### Tạo class file bằng Builder

Class-File API dùng builder để tạo cấu trúc class file. Mỗi cấp có builder tương ứng: `ClassBuilder` cho class, `MethodBuilder` cho method và `CodeBuilder` cho bytecode.

Ví dụ sau tạo class `HelloGenerated` có constructor và method `main` in một dòng chữ:

```java
import java.lang.classfile.ClassFile;
import java.lang.constant.ClassDesc;
import java.lang.constant.MethodTypeDesc;
import java.nio.file.Files;
import java.nio.file.Path;

import static java.lang.constant.ConstantDescs.CD_Object;
import static java.lang.constant.ConstantDescs.CD_String;
import static java.lang.constant.ConstantDescs.CD_void;
import static java.lang.constant.ConstantDescs.INIT_NAME;
import static java.lang.constant.ConstantDescs.MTD_void;

public class GenerateClassFile {
    public static void main(String[] args) throws Exception {
        ClassDesc generatedClass = ClassDesc.of("HelloGenerated");
        ClassDesc systemClass = ClassDesc.of("java.lang.System");
        ClassDesc printStreamClass = ClassDesc.of("java.io.PrintStream");

        MethodTypeDesc mainDescriptor =
                MethodTypeDesc.of(CD_void, CD_String.arrayType());
        MethodTypeDesc printlnDescriptor =
                MethodTypeDesc.of(CD_void, CD_String);

        byte[] bytes = ClassFile.of().build(generatedClass,
                classBuilder -> classBuilder
                        .withVersion(ClassFile.JAVA_24_VERSION, 0)
                        .withFlags(ClassFile.ACC_PUBLIC)
                        .withMethodBody(INIT_NAME, MTD_void, ClassFile.ACC_PUBLIC,
                                code -> code.aload(0)
                                        .invokespecial(CD_Object, INIT_NAME, MTD_void)
                                        .return_())
                        .withMethodBody("main", mainDescriptor,
                                ClassFile.ACC_PUBLIC | ClassFile.ACC_STATIC,
                                code -> code.getstatic(systemClass, "out", printStreamClass)
                                        .ldc("Hello from Class-File API")
                                        .invokevirtual(printStreamClass, "println", printlnDescriptor)
                                        .return_())
        );

        Files.write(Path.of("HelloGenerated.class"), bytes);
    }
}
```

Sau khi chạy `GenerateClassFile`, file `HelloGenerated.class` được tạo. Có thể chạy class vừa tạo bằng:

```shell
java HelloGenerated
```

Kết quả:

```text
Hello from Class-File API
```

Ví dụ đặt class file version là `ClassFile.JAVA_24_VERSION` để tạo bytecode tương thích với JDK 24 trở lên. Nếu bỏ `withVersion`, builder sử dụng phiên bản class file mặc định của runtime đang chạy chương trình tạo mã. Khi cần hỗ trợ runtime cũ hơn, phải kiểm tra cả class file version lẫn các bytecode, attribute và API mà class được sinh ra sử dụng.

### Biến đổi class file

Một công việc thường gặp là đọc class hiện có, giữ phần lớn cấu trúc và chỉ thay đổi một số element. `ClassTransform` mô tả thao tác này; `ClassFile.transformClass` tạo byte array mới từ model và transform.

Ví dụ sau loại các method có tên bắt đầu bằng `debug_`:

```java
import java.io.IOException;
import java.lang.classfile.ClassFile;
import java.lang.classfile.ClassModel;
import java.lang.classfile.ClassTransform;
import java.lang.classfile.MethodModel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

public class TransformClassFile {
    public static void main(String[] args) throws IOException {
        ClassFile classFile = ClassFile.of();
        Path input = Path.of(args[0]); // Ví dụ: Example.class trong default package
        ClassModel original = classFile.parse(input);

        ClassTransform removeDebugMethods = ClassTransform.dropping(
                element -> element instanceof MethodModel method
                        && method.methodName().stringValue().startsWith("debug_")
        );

        byte[] transformed = classFile.transformClass(original, removeDebugMethods);
        List<VerifyError> errors = classFile.verify(transformed);

        if (!errors.isEmpty()) {
            throw new IllegalStateException("Class file verification failed: " + errors);
        }

        Path output = Path.of("out").resolve(input.getFileName());
        Files.createDirectories(output.getParent());
        Files.write(output, transformed);
    }
}
```

Transform có thể giữ nguyên element bằng cách đưa element vào builder, bỏ element bằng cách không thêm nó, hoặc thay element bằng một hay nhiều element mới. Các transform cùng cấp có thể được nối bằng `andThen`; transform ở cấp code có thể được nâng lên cấp method hoặc class bằng các factory method như `MethodTransform.transformingCode(...)` và `ClassTransform.transformingMethods(...)`.

Trong ví dụ, class được giữ nguyên tên và nằm trong default package nên file kết quả là `out/Example.class`. Với class thuộc package có tên, cần giữ đúng cấu trúc thư mục package bên dưới thư mục output để đường dẫn khớp với binary name của class.

Ví dụ loại method chỉ minh họa cách lọc element. Trong ứng dụng thực tế, xóa method có thể phá vỡ lời gọi từ class khác, reflection, framework, serialization hoặc hợp đồng API. Cần phân tích dependency và kiểm thử các class liên quan trước khi sử dụng transform làm bước xử lý bytecode trong production.

### Kiểm tra và những giới hạn cần biết

`ClassFile.verify(...)` trả về danh sách `VerifyError` phát hiện trong quá trình kiểm tra class file. Đây là bước kiểm tra hữu ích sau khi tạo hoặc biến đổi bytecode, nhưng không chứng minh chương trình có hành vi đúng về mặt nghiệp vụ. Vẫn cần kiểm thử việc liên kết và chạy class trong môi trường đích.

Một số giới hạn quan trọng:

- Runtime chỉ parse được class file version mà phiên bản JDK đó hỗ trợ. `parse` có thể ném `IllegalArgumentException` nếu file sai cấu trúc hoặc có version chưa được runtime hỗ trợ.
- Parse lazy nên lỗi dữ liệu hỏng có thể xuất hiện khi truy cập model hoặc element.
- API cung cấp mapper cho các attribute chuẩn. Nếu cần đọc attribute riêng của công cụ khác, phải cấu hình `AttributeMapper` phù hợp; attribute không nhận diện có thể được biểu diễn dưới dạng `UnknownAttribute` với nội dung byte thô.
- Builder không tự thực hiện mọi kiểm tra nhất quán ở thời điểm thêm element. Một cấu trúc không hợp lệ có thể dẫn tới lỗi khi build hoặc verify.
- Transform cần quyết định rõ cách xử lý element chưa biết. Nếu chỉ thay đổi một phần cấu trúc, thường nên chuyển nguyên trạng các element không liên quan bằng `builder.with(element)`.
- Khi xử lý class file không tin cậy, cần coi dữ liệu đầu vào là dữ liệu nhị phân có thể lỗi hoặc được tạo có chủ đích để gây tốn tài nguyên. Parse và verify không phải cơ chế sandbox cho bytecode.

### Khi nào nên dùng Class-File API?

Class-File API phù hợp với công cụ hoặc thư viện cần thao tác ở cấp bytecode:

- Đọc metadata, field, method và instruction để phân tích dependency hoặc kiểm tra cấu trúc class.
- Tạo class file hoặc method bytecode trong công cụ sinh mã.
- Biến đổi method body, thay lời gọi, thêm instrumentation hoặc loại bỏ element theo quy tắc cụ thể.
- Xây dựng agent, bộ phân tích hoặc công cụ phát triển cần một API class file được JDK chuẩn hóa.

Nếu chỉ cần gọi method hoặc đọc annotation của một class đã được nạp, Reflection thường phù hợp hơn. Nếu cần biên dịch hoặc phân tích mã nguồn Java, hãy chọn Compiler API. Nếu cần xử lý bytecode, Class-File API là lựa chọn chuẩn có sẵn trong JDK 24 trở lên.

## Kết hợp hai tính năng trong công việc Java hiện đại

Stream Gatherers và Class-File API không phụ thuộc vào nhau, nhưng có thể xuất hiện trong cùng một công cụ phát triển. Chẳng hạn, một chương trình phân tích thư mục build có thể:

1. Duyệt các file `.class` và tạo stream đường dẫn.
2. Dùng `mapConcurrent` với giới hạn đồng thời để parse nhiều class file độc lập.
3. Dùng Class-File API đọc method, field và instruction của từng class.
4. Dùng Gatherer tùy chỉnh để gom các cảnh báo hoặc dependency thành nhóm theo quy tắc của công cụ.
5. Tổng hợp kết quả bằng terminal operation như `toList()` hoặc `collect(...)`.

Ví dụ này cho thấy mỗi API giải quyết một lớp vấn đề: Gatherer tổ chức luồng dữ liệu trong chương trình Java; Class-File API hiểu và thay đổi cấu trúc bytecode.

## Ghi nhớ

- Stream Gatherers được preview trong JDK 22 và 23, chính thức từ JDK 24 qua JEP 485. Dùng `Stream.gather`, `Gatherer` và `Gatherers` cho intermediate operation tùy chỉnh, có trạng thái hoặc phát ra nhiều phần tử.
- Class-File API được preview trong JDK 22 và 23, chính thức từ JDK 24 qua JEP 484. Dùng package `java.lang.classfile` để parse, build, transform và verify file `.class`.
- Khi viết mã mới, hãy dùng API final từ JDK 24 trở lên. Chỉ cần bật preview khi chủ động nghiên cứu hoặc tái hiện lịch sử API ở các JDK 22/23.
- Hãy chọn operation đơn giản có sẵn trước khi tự viết Gatherer; chỉ bật xử lý song song khi combiner đúng với logic.
- Với bytecode, luôn quan tâm đến class file version, attribute, dependency và việc kiểm thử class sau biến đổi.

## Tài liệu tham khảo

### JEP

- [JEP 461 — Stream Gatherers (Preview, JDK 22)](https://openjdk.org/jeps/461)
- [JEP 473 — Stream Gatherers (Second Preview, JDK 23)](https://openjdk.org/jeps/473)
- [JEP 485 — Stream Gatherers (JDK 24)](https://openjdk.org/jeps/485)
- [JEP 457 — Class-File API (Preview, JDK 22)](https://openjdk.org/jeps/457)
- [JEP 466 — Class-File API (Second Preview, JDK 23)](https://openjdk.org/jeps/466)
- [JEP 484 — Class-File API (JDK 24)](https://openjdk.org/jeps/484)

### Java SE API và hướng dẫn

- [Java SE 27 API — `Gatherer`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/Gatherer.html)
- [Java SE 27 API — `Gatherers`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/Gatherers.html)
- [Java SE 27 API — `Stream.gather`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/Stream.html)
- [Java SE 27 API — Package `java.lang.classfile`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/classfile/package-summary.html)
- [Java SE 27 API — `ClassFile`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/classfile/ClassFile.html)
- [Java Virtual Machine Specification — The `class` File Format](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-4.html)
