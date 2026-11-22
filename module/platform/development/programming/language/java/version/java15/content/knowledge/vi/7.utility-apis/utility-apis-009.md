# Byte.describeConstable và Short.describeConstable trong Java 15+

## 1. Khái niệm và mục đích

`java.lang.Byte` và `java.lang.Short` là hai lớp wrapper cho các kiểu nguyên thủy `byte` và `short`. Từ **Java 15**, cả hai có phương thức instance `describeConstable()`, được cung cấp nhằm **mô tả danh nghĩa (nominal description)** của giá trị wrapper để dùng trong các API liên quan đến hằng số và constant pool của Java class file.

Một *nominal descriptor* là đối tượng mô tả cách nhận diện hoặc tái tạo một giá trị hằng, **không phải bản thân giá trị wrapper**. Khi xử lý dữ liệu số thường ngày, bạn hầu như không cần API này: toán học sử dụng `byte`/`short`, chuyển chuỗi dùng `parseByte`/`parseShort`, tạo wrapper dùng `valueOf`.

Đây là các phương thức chính thức từ Java 15, còn được hỗ trợ trong Java hiện đại. Nội dung dưới đây dùng cú pháp phù hợp Java 17+ và chỉ đề cập đến cơ chế/API vẫn có hiệu lực.

## 2. Phân biệt số nguyên thủy, wrapper và descriptor

| Loại | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Primitive `byte` | `byte raw = -12;` | Giá trị số nguyên có dấu 8 bit, từ -128 đến 127 |
| Primitive `short` | `short count = 300;` | Giá trị số nguyên có dấu 16 bit, từ -32768 đến 32767 |
| Wrapper `Byte` | `Byte.valueOf((byte) -12)` | Đối tượng `Byte` đại diện giá trị số |
| Wrapper `Short` | `Short.valueOf((short) 300)` | Đối tượng `Short` đại diện giá trị số |
| Descriptor | `wrapper.describeConstable().orElseThrow()` | Đối tượng mô tả cách biểu diễn hoặc tái tạo giá trị wrapper |

Ví dụ ngắn:

```java
byte raw = -12;
Byte wrapped = Byte.valueOf(raw);

// Đây là phương thức của đối tượng Byte, không phải của primitive byte.
var descriptor = wrapped.describeConstable();
```

`wrapped` chứa giá trị kiểu `Byte`; `descriptor` có kiểu `Optional<DynamicConstantDesc<Byte>>`. Sự khác biệt này rất quan trọng: `Optional` không chứa một `Byte` khác mà chứa **mô tả của giá trị Byte**.

## 3. `Constable`, `ConstantDesc`, `DynamicConstantDesc`

### 3.1. `Constable` là hợp đồng gì?

Giao diện `java.lang.constant.Constable` áp dụng cho những kiểu có instance có thể tự cung cấp một mô tả dạng `ConstantDesc`. Chữ ký tổng quát:

```java
Optional<? extends ConstantDesc> describeConstable();
```

Với một số triển khai của `Constable`, không phải instance nào cũng có mô tả danh nghĩa thích hợp, nên kết quả được bao trong `Optional`: có thể có descriptor hoặc không có descriptor. Điều này giúp các công cụ làm việc với nhiều kiểu `Constable` theo cùng một hợp đồng.

### 3.2. `ConstantDesc` mô tả hằng số như thế nào?

`java.lang.constant.ConstantDesc` là dạng mô tả danh nghĩa của một giá trị có thể biểu diễn như hằng số. Nó giống một **công thức mô tả hằng số**, cho phép API xử lý class file giữ thông tin tượng trưng và có thể phân giải ra giá trị trong môi trường thích hợp.

Một descriptor không phải nơi lưu dữ liệu người dùng tùy ý như JSON và không có nghĩa là nội dung của nó tự động được ghi vào constant pool chỉ vì ta gọi `describeConstable()`.

### 3.3. Vì sao kết quả lại là `DynamicConstantDesc<T>`?

`java.lang.constant.DynamicConstantDesc<T>` là một dạng `ConstantDesc` mô tả dynamic constant, liên hệ với mục `CONSTANT_Dynamic_info` trong JVM class-file constant pool. Nó có đủ thông tin tượng trưng cần thiết để phân giải giá trị qua cơ chế bootstrap và ngữ cảnh truy cập.

`Byte` và `Short` là wrapper, và mô tả của chúng cần biểu diễn **đúng giá trị lẫn kiểu wrapper**. Vì thế kết quả là `DynamicConstantDesc<Byte>` hoặc `DynamicConstantDesc<Short>`, không đơn thuần là một giá trị `int` hay một chuỗi số.

Đừng suy luận rằng mọi lớp `Constable` đều trả về `DynamicConstantDesc`: một số kiểu nền tảng có mô tả trực tiếp hơn và chữ ký trả về riêng.

## 4. Chữ ký và so sánh hai phương thức

Hai phương thức không nhận tham số và đều là **instance method**:

```java
// Trên đối tượng java.lang.Byte
public Optional<DynamicConstantDesc<Byte>> describeConstable();

// Trên đối tượng java.lang.Short
public Optional<DynamicConstantDesc<Short>> describeConstable();
```

| Tiêu chí | `Byte.describeConstable()` | `Short.describeConstable()` |
| --- | --- | --- |
| Có từ phiên bản | Java 15 | Java 15 |
| Gọi trên đối tượng | `byteObject.describeConstable()` | `shortObject.describeConstable()` |
| Kiểu trả về chính xác | `Optional<DynamicConstantDesc<Byte>>` | `Optional<DynamicConstantDesc<Short>>` |
| Loại giá trị được mô tả | Wrapper `Byte` | Wrapper `Short` |
| Phạm vi giá trị | -128 đến 127 | -32768 đến 32767 |
| Giá trị khi phân giải đúng | `Byte` cùng giá trị | `Short` cùng giá trị |

Ví dụ khai báo tường minh:

```java
import java.lang.constant.DynamicConstantDesc;
import java.util.Optional;

Byte b = Byte.valueOf((byte) 25);
Short s = Short.valueOf((short) 500);

Optional<DynamicConstantDesc<Byte>> byteDesc = b.describeConstable();
Optional<DynamicConstantDesc<Short>> shortDesc = s.describeConstable();
```

Đây là **đoạn trích minh họa**; các câu lệnh đặt bên trong phương thức hoặc test đã có, còn bản có `main` đầy đủ nằm ở phần 6.

## 5. Luồng tạo mô tả và tái tạo giá trị

Quy trình tổng quát:

```text
Byte hoặc Short đang có
          |
          |  describeConstable()
          v
Optional<DynamicConstantDesc<Byte hoặc Short>>
          |
          |  Kiểm tra Optional; lấy descriptor
          v
DynamicConstantDesc<Byte hoặc Short>
          |
          |  resolveConstantDesc(MethodHandles.Lookup)
          v
Giá trị Byte hoặc Short được tái tạo
```

Sau khi lấy descriptor, có thể phân giải:

```java
Byte restored = byteDesc.orElseThrow()
        .resolveConstantDesc(java.lang.invoke.MethodHandles.lookup());
```

Trong đó:

- `orElseThrow()` lấy descriptor ra khỏi `Optional`; nếu rỗng thì ném `NoSuchElementException`.
- `resolveConstantDesc(...)` dùng một `MethodHandles.Lookup` cung cấp ngữ cảnh phân giải tên lớp, phương thức và quyền truy cập.
- Kết quả phân giải từ `DynamicConstantDesc<Byte>` có kiểu `Byte`; từ `DynamicConstantDesc<Short>` có kiểu `Short`.
- Phân giải có thể phát sinh `ReflectiveOperationException`; ví dụ hoàn chỉnh cho phép truyền ngoại lệ qua `throws` để tập trung vào API đang học.

**Đây không phải chuyển đổi chuỗi sang số.** Descriptor là một dạng biểu diễn phục vụ cơ chế hằng số của JVM; khi chỉ cần tính toán hoặc in số, dùng giá trị wrapper/primitive sẵn có.

## 6. Ví dụ hoàn chỉnh: Java 17+ và kết quả kiểm chứng

Tạo file `ByteShortConstableDemo.java`:

```java
import java.lang.constant.DynamicConstantDesc;
import java.lang.invoke.MethodHandles;
import java.util.Optional;

public class ByteShortConstableDemo {
    public static void main(String[] args) throws ReflectiveOperationException {
        Byte b = Byte.valueOf((byte) -12);
        Short s = Short.valueOf((short) 300);

        Optional<DynamicConstantDesc<Byte>> byteDesc = b.describeConstable();
        Optional<DynamicConstantDesc<Short>> shortDesc = s.describeConstable();

        System.out.println("Byte descriptor present: " + byteDesc.isPresent());
        System.out.println("Short descriptor present: " + shortDesc.isPresent());

        Byte restoredByte = byteDesc.orElseThrow()
                .resolveConstantDesc(MethodHandles.lookup());
        Short restoredShort = shortDesc.orElseThrow()
                .resolveConstantDesc(MethodHandles.lookup());

        System.out.println("Byte restored: " + restoredByte);
        System.out.println("Short restored: " + restoredShort);
        System.out.println("Values match: " + b.equals(restoredByte)
                + ", " + s.equals(restoredShort));

        System.out.println("Byte bounds describable: "
                + Byte.valueOf(Byte.MIN_VALUE).describeConstable().isPresent()
                + ", "
                + Byte.valueOf(Byte.MAX_VALUE).describeConstable().isPresent());

        System.out.println("Short bounds describable: "
                + Short.valueOf(Short.MIN_VALUE).describeConstable().isPresent()
                + ", "
                + Short.valueOf(Short.MAX_VALUE).describeConstable().isPresent());
    }
}
```

Biên dịch rồi chạy với JDK 17 trở lên:

```bash
javac ByteShortConstableDemo.java
java ByteShortConstableDemo
```

Stdout chính xác, đã chạy kiểm chứng bằng JDK 24 với chế độ source Java 17:

```text
Byte descriptor present: true
Short descriptor present: true
Byte restored: -12
Short restored: 300
Values match: true, true
Byte bounds describable: true, true
Short bounds describable: true, true
```

**Cách giải thích output:**

1. Cả `b` và `s` có nominal descriptor, do đó hai `Optional` đều có phần tử.
2. Hai descriptor được phân giải thành giá trị `Byte` -12 và `Short` 300. Không có chuyển đổi kiểu bất ngờ: `Byte` vẫn là `Byte`, `Short` vẫn là `Short`.
3. `b.equals(restoredByte)` và `s.equals(restoredShort)` đều `true`, chứng minh việc tái tạo giữ đúng giá trị.
4. Giá trị biên âm/dương của `Byte` và `Short` vẫn cho descriptor. Hai lớp biểu diễn các dải số nguyên hữu hạn nên giá trị wrapper hợp lệ có thể được mô tả.
5. Không cần kiểm tra `==`: identity của wrapper không phải tiêu chí đánh giá tính đúng của descriptor.

Việc chọn `Short` bằng 300 tránh phụ thuộc phạm vi cache wrapper phổ biến khi người học muốn thử lại trên các JVM khác nhau; chương trình vẫn kiểm tra bằng so sánh giá trị.

## 7. Vì sao kết quả bọc trong `Optional`?

Theo thiết kế của `Constable`, có những kiểu mà một số instance không thể tạo nominal descriptor phù hợp, vì thế interface trả về `Optional`. Trong khi đó, tài liệu API của `Byte` và `Short` mô tả kết quả là `Optional` **chứa descriptor cho instance**; chương trình ở trên xác minh các giá trị thông thường và cực trị.

Với hàm dùng chung cho nhiều kiểu `Constable`, đừng luôn gọi `get()` mà bỏ qua khả năng `Optional` rỗng. Có thể viết:

```java
import java.lang.constant.Constable;
import java.lang.constant.ConstantDesc;
import java.util.Optional;

static Optional<? extends ConstantDesc> describe(Constable value) {
    return value.describeConstable();
}
```

Đây là phương thức minh họa cần đặt trong một lớp Java. Nó giữ kiểu trả về tổng quát theo interface, phù hợp với các implementation khác nhau. Nếu xử lý riêng `Byte` hoặc `Short`, giữ đúng kiểu trả về cụ thể `Optional<DynamicConstantDesc<Byte>>` hoặc `Optional<DynamicConstantDesc<Short>>` giúp trình biên dịch kiểm tra kiểu tốt hơn.

Khi xử lý các descriptor thực sự được lấy ra từ `Optional`, phần mềm nên định nghĩa rõ hành vi khi không có descriptor và khi việc phân giải thất bại. Trong chương trình demo, `orElseThrow()` chỉ dùng sau khi biết dữ liệu thuộc hai lớp wrapper có mô tả tương ứng.

## 8. Khi nào API này có giá trị thực tế?

Các API `java.lang.constant` được thiết kế để thao tác với **mô tả danh nghĩa của hằng số**. Một số ứng dụng hợp lý:

- Công cụ tạo, đọc hoặc phân tích **class file** và **bytecode**.
- Thư viện cần chuyển instance `Constable` thành `ConstantDesc` để truyền vào API xử lý constant pool.
- Công cụ kiểm thử hoặc kiểm chứng tính nhất quán giữa một descriptor và giá trị nó phân giải.
- Lớp trừu tượng làm việc với nhiều loại hằng số mà không muốn buộc caller phải chuyển mọi thứ sang chuỗi.

Khi các công cụ cần diễn tả một wrapper `Byte` hoặc `Short`, `describeConstable()` cung cấp cách chuẩn hóa quá trình này theo Java API hiện hành.

Ngược lại, những tác vụ sau không cần nó: cộng trừ nhân chia số, chuyển số sang chuỗi, đọc số từ input, gửi JSON qua REST API, hoặc lưu cột số trong database. Dùng `describeConstable()` ở những tác vụ đó làm luồng xử lý khó hiểu hơn mà không phục vụ nhu cầu dữ liệu.

## 9. Phân biệt với các API số nguyên thường dùng

| Mục đích | Cách gọi đúng | Kết quả |
| --- | --- | --- |
| Đọc `byte` từ văn bản | `Byte.parseByte("12")` | Primitive `byte` |
| Đọc `short` từ văn bản | `Short.parseShort("300")` | Primitive `short` |
| Lấy wrapper từ primitive | `Byte.valueOf((byte) 12)` | `Byte` |
| Lấy wrapper từ primitive | `Short.valueOf((short) 300)` | `Short` |
| Lấy primitive từ wrapper | `b.byteValue()`, `s.shortValue()` | `byte`, `short` |
| Mô tả hằng số wrapper | `b.describeConstable()` | `Optional<DynamicConstantDesc<Byte>>` |
| Mô tả hằng số wrapper | `s.describeConstable()` | `Optional<DynamicConstantDesc<Short>>` |
| Phân giải lại mô tả | `descriptor.resolveConstantDesc(lookup)` | Giá trị của wrapper tương ứng |

Điểm cần thuộc: **`describeConstable()` không trả về `Optional<Byte>` hoặc `Optional<Short>`**. Nếu chỉ cần trả về số, không cần mô tả constant pool.

## 10. Giá trị số, kiểu wrapper và identity

`Byte` và `Short` là wrapper có giá trị (*value-based classes*) trong Java hiện đại. Chương trình nên đối xử với những instance bằng nhau như các giá trị tương đương; tránh dùng object identity cho điều kiện nghiệp vụ hoặc đồng bộ hóa.

Ví dụ:

```java
Byte x = Byte.valueOf((byte) 12);
Byte y = Byte.valueOf((byte) 12);
boolean sameValue = x.equals(y); // true
```

Không nên dùng `x == y` làm bằng chứng cho việc descriptor đã tái tạo đúng giá trị: nhiều giá trị wrapper được cache, nhưng không nên xây dựng logic dựa vào identity. Hãy so sánh bằng `equals` hay giải nén thành primitive tùy bài toán.

Ngoài ra, `Byte.valueOf((byte) 12).equals(Short.valueOf((short) 12))` là `false`, dù cùng có trị số 12, vì hai wrapper có loại khác nhau. Descriptor giữ lại loại tương ứng và không tự chuyển `Byte` thành `Short`.

`Byte` và `Short` đều biểu diễn số nguyên có dấu. `describeConstable()` không tự chuyển một số âm thành unsigned; nếu cần unsigned, dùng các API `Byte.toUnsignedInt(byteValue)` và `Short.toUnsignedInt(shortValue)` theo mục đích riêng.

## 11. Lỗi thường gặp

1. **Gọi trên primitive:** `byte n = 7; n.describeConstable();` không biên dịch vì `byte` không có method; phải gọi trên đối tượng `Byte`.
2. **Nhầm `Optional` chứa số:** kết quả là `Optional` chứa **descriptor**, không chứa wrapper gốc.
3. **Dùng `Byte.describeConstable()` như static method:** phương thức là instance method, cần `b.describeConstable()`.
4. **Bỏ qua `Optional.empty()` trong code tổng quát:** interface `Constable` không cam kết mọi instance của mọi loại đều mô tả được.
5. **Bỏ qua ngữ cảnh khi phân giải:** `resolveConstantDesc` yêu cầu `Lookup` và có thể ném `ReflectiveOperationException`.
6. **So sánh object bằng `==`:** không xác minh được cùng giá trị trong mọi điều kiện; dùng `equals`.
7. **Lưu `descriptor.toString()` rồi dự định parse ngược:** chuỗi mô tả dành cho hiển thị/gỡ lỗi, không phải định dạng dữ liệu liên ứng dụng ổn định.
8. **Dùng cơ chế descriptor thay cho parse/serialization:** đây là API cho constant descriptions/classfile tooling, không phải bộ chuyển đổi dữ liệu người dùng.
9. **Sử dụng constructor wrapper cũ:** với code hiện đại, dùng `Byte.valueOf` và `Short.valueOf` thay vì constructor wrapper đã deprecated.

## 12. Ghi nhớ

- Hai phương thức `Byte.describeConstable()` và `Short.describeConstable()` được giới thiệu từ **Java 15**, vẫn còn hỗ trợ.
- Chúng là phương thức **instance** không nhận tham số; trả về `Optional<DynamicConstantDesc<Byte>>` hoặc `Optional<DynamicConstantDesc<Short>>`.
- Descriptor là mô tả danh nghĩa của giá trị wrapper, có thể được phân giải bằng `resolveConstantDesc(MethodHandles.Lookup)` trong ngữ cảnh thích hợp.
- Tập trung kiểm tra **đúng loại wrapper và đúng giá trị**, dùng `equals`; hiểu cách xử lý `Optional` và ngoại lệ.
- Chỉ dùng API này khi một phần mềm thực sự cần làm việc với **constant descriptions, JVM class files hoặc bytecode**.

## Tài liệu Oracle hiện hành

- [Byte — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Byte.html#describeConstable()): chữ ký của `Byte.describeConstable()`, mốc *Since: 15*.
- [Short — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Short.html#describeConstable()): chữ ký của `Short.describeConstable()`, mốc *Since: 15*.
- [Constable — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/constant/Constable.html): hợp đồng `Optional` và ý nghĩa nominal descriptor.
- [DynamicConstantDesc — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/constant/DynamicConstantDesc.html): mô tả dynamic constants.
- [java.lang.constant — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/constant/package-summary.html): tổng quan ConstantDesc, constant pool và quá trình phân giải.

Bài học chỉ trình bày API chính thức đang được hỗ trợ, không sử dụng các cơ chế preview hoặc legacy.