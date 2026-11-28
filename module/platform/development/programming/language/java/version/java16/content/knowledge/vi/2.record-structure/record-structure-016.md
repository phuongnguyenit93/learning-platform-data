# Dùng javap để đối chiếu component, constructor và thành viên được sinh

## 1. Vì sao cần dùng javap khi học record?

Khi khai báo một record, mã nguồn thường ngắn hơn class thông thường vì Java tự cung cấp nhiều thành viên dựa trên record header. Để hiểu compiler đã đưa những gì vào file bytecode, có thể dùng công cụ `javap` đi kèm JDK.

`javap` là công cụ disassemble class file. Nó đọc file `.class` và hiển thị thông tin về class, field, constructor, method, descriptor, attribute và bytecode. Khi dùng với record, công cụ giúp đối chiếu:

- Component được khai báo trong record header.
- Field instance tương ứng với component.
- Canonical constructor.
- Accessor cho từng component.
- Các method giá trị mặc định như `equals(Object)`, `hashCode()` và `toString()`.
- Các method, field static hoặc constructor do lập trình viên tự khai báo.

Record được hoàn thiện trong Java 16. Các thông tin class file và cách dùng `javap` trong bài này vẫn áp dụng với Java hiện đại.

Mục tiêu bài học:

- Biên dịch record thành class file để kiểm tra.
- Chọn tùy chọn `javap` phù hợp cho từng loại thông tin.
- Đọc `Record` attribute và descriptor của component.
- Đối chiếu field, canonical constructor, accessor và method giá trị.
- Nhận biết phần do compiler sinh và phần do lập trình viên khai báo.
- Hiểu giới hạn của bytecode inspection và tránh phụ thuộc vào chi tiết triển khai.

## 2. Chuẩn bị một record để kiểm tra

Tạo file `src/demo/Person.java`:

~~~java
package demo;

import java.util.Objects;

public record Person(String name, int age) {
    public static final int ADULT_AGE = 18;

    public Person {
        name = Objects.requireNonNull(name, "name").strip();

        if (name.isEmpty()) {
            throw new IllegalArgumentException("name is required");
        }
        if (age < 0) {
            throw new IllegalArgumentException("age must be non-negative");
        }
    }

    public boolean isAdult() {
        return age >= ADULT_AGE;
    }
}
~~~

Record có hai component:

- `name` có kiểu `String`.
- `age` có kiểu `int`.

Ngoài các thành viên được sinh tự động, mã nguồn còn khai báo:

- Compact canonical constructor để chuẩn hóa và xác thực dữ liệu.
- Instance method `isAdult()`.
- Static final constant `ADULT_AGE`.

Biên dịch bằng JDK 16 trở lên:

~~~bash
javac --release 16 -d out src/demo/Person.java
~~~

Ý nghĩa tùy chọn:

- `--release 16` yêu cầu compiler biên dịch theo nền tảng Java 16, bao gồm mức ngôn ngữ, API và định dạng class file tương ứng.
- `-d out` đặt file class đầu ra vào thư mục `out` theo cấu trúc package.
- `src/demo/Person.java` là file nguồn.

Sau khi biên dịch, file cần kiểm tra nằm tại `out/demo/Person.class`.

Có thể xác nhận phiên bản công cụ:

~~~bash
javac --version
javap --version
~~~

Dùng `javap` thuộc JDK đang sử dụng để tránh nhầm lẫn giữa compiler và công cụ disassemble từ những JDK khác nhau.

## 3. Các tùy chọn javap thường dùng

`javap` có nhiều tùy chọn. Những tùy chọn sau hữu ích nhất khi kiểm tra record:

| Tùy chọn | Ý nghĩa | Khi nên dùng |
| --- | --- | --- |
| `-p` hoặc `-private` | Hiển thị cả thành viên private. | Xem field component private và các thành viên không public. |
| `-s` | Hiển thị internal type signature/descriptor. | Đối chiếu kiểu JVM của field và method. |
| `-c` | Disassemble bytecode của method. | Xem constructor và method thực thi như thế nào. |
| `-v` hoặc `-verbose` | Hiển thị thông tin class file chi tiết. | Xem Record attribute, flags, descriptor, bootstrap metadata. |
| `-constants` | Hiển thị giá trị hằng số static final phù hợp. | Kiểm tra constant variable. |
| `-l` | Hiển thị line number và local variable tables nếu có. | Liên hệ bytecode với mã nguồn khi debug. |
| `-classpath` | Chỉ định nơi tìm class. | Kiểm tra class trong thư mục build riêng. |

Xem cấu trúc công khai và private:

~~~bash
javap -classpath out -p demo.Person
~~~

Xem descriptor:

~~~bash
javap -classpath out -p -s demo.Person
~~~

Xem bytecode:

~~~bash
javap -classpath out -p -c demo.Person
~~~

Xem đầy đủ metadata:

~~~bash
javap -classpath out -p -v demo.Person
~~~

Có thể kết hợp các tùy chọn, ví dụ `-p -c -v`. Với lần kiểm tra đầu tiên, lệnh `javap -classpath out -p -v demo.Person` thường cung cấp đủ thông tin để tìm component và các method.

## 4. Đọc danh sách field và method

Chạy:

~~~bash
javap -classpath out -p demo.Person
~~~

Kết quả rút gọn có dạng tương tự:

~~~text
Compiled from "Person.java"
public final class demo.Person extends java.lang.Record {
  private final java.lang.String name;
  private final int age;
  public static final int ADULT_AGE;
  public demo.Person(java.lang.String, int);
  public java.lang.String name();
  public int age();
  public boolean isAdult();
  public final boolean equals(java.lang.Object);
  public final int hashCode();
  public final java.lang.String toString();
}
~~~

Thứ tự hiển thị và modifier chi tiết có thể thay đổi theo compiler hoặc JDK. Hãy tập trung vào cấu trúc và chữ ký:

### Field tương ứng với component

Hai dòng:

~~~text
private final java.lang.String name;
private final int age;
~~~

cho thấy record có field instance private final tương ứng với component `name` và `age`.

Không có field instance bổ sung nào trong ví dụ. Hằng số `ADULT_AGE` là field static final, không phải component.

### Canonical constructor

Dòng:

~~~text
public demo.Person(java.lang.String, int);
~~~

là canonical constructor, nhận đúng các tham số tương ứng với component theo thứ tự trong header.

Vì record khai báo compact canonical constructor, compiler vẫn tạo constructor với danh sách tham số đầy đủ và thực thi phần xác thực/chuẩn hóa đã viết trong body. Compact syntax chỉ rút gọn cách viết ở mã nguồn; nó không loại bỏ constructor khỏi class file.

### Accessor

Hai method:

~~~text
public java.lang.String name();
public int age();
~~~

là accessor của component. Tên accessor trùng tên component và không có tiền tố `get`.

### Method giá trị của record

Các method `equals(Object)`, `hashCode()` và `toString()` có mặt dù không được khai báo trong mã nguồn ví dụ. Đây là các method record cung cấp ngầm định khi lập trình viên không tự khai báo chúng.

### Method do người viết khai báo

`isAdult()` xuất hiện vì mã nguồn khai báo phương thức này. `ADULT_AGE` là thành viên static được khai báo tường minh.

`javap` cho biết method nào tồn tại trong class file; để xác định một method là implicit hay explicit, cần đối chiếu class file với mã nguồn và quy tắc ngôn ngữ Java.

## 5. Đọc descriptor bằng tùy chọn -s

JVM dùng descriptor để biểu diễn kiểu của field và method trong class file. Descriptor không giống cú pháp kiểu Java ở mã nguồn.

Chạy:

~~~bash
javap -classpath out -p -s demo.Person
~~~

Các descriptor quan trọng trong ví dụ:

| Thành viên | Kiểu Java | Descriptor |
| --- | --- | --- |
| Field `name` | `String` | `Ljava/lang/String;` |
| Field `age` | `int` | `I` |
| Constructor `Person(String, int)` | Không có kiểu trả về trong Java source | `(Ljava/lang/String;I)V` |
| Accessor `name()` | `String` | `()Ljava/lang/String;` |
| Accessor `age()` | `int` | `()I` |
| Method `isAdult()` | `boolean` | `()Z` |
| Method `equals(Object)` | `boolean` | `(Ljava/lang/Object;)Z` |

Một số ký hiệu descriptor thường gặp:

| Descriptor | Kiểu |
| --- | --- |
| `I` | `int` |
| `Z` | `boolean` |
| `J` | `long` |
| `D` | `double` |
| `V` | `void` |
| `Ljava/lang/String;` | Kiểu tham chiếu `java.lang.String` |
| `[I` | Mảng `int[]` |
| `[Ljava/lang/String;` | Mảng `String[]` |

Constructor có descriptor kết thúc bằng `V` vì constructor không trả về giá trị trong JVM descriptor. Tên constructor trong class file là `<init>`; khi trình bày theo cú pháp Java, `javap` hiển thị tên class.

Descriptor hữu ích khi đọc bytecode, kiểm tra overload hoặc phân tích API ở cấp JVM. Trong sử dụng Java hằng ngày, không cần tự viết descriptor khi khai báo record.

## 6. Tìm Record attribute bằng -v

Record component không chỉ xuất hiện dưới dạng field và accessor. Class file của record còn có `Record` attribute lưu metadata của các component.

Chạy:

~~~bash
javap -classpath out -p -v demo.Person
~~~

Tìm phần có tiêu đề:

~~~text
Record:
  java.lang.String name;
    descriptor: Ljava/lang/String;
  int age;
    descriptor: I
~~~

Đây là phần quan trọng để đối chiếu record header:

- Tên component được lưu trong Record attribute.
- Kiểu component được lưu dưới dạng descriptor.
- Thứ tự component được giữ theo record header.
- Metadata này cho phép công cụ và reflection nhận diện cấu trúc record.

Cần phân biệt ba thứ liên quan nhưng khác nhau:

1. **Record component:** phần tử trong record header và metadata của class file.
2. **Field component:** field private final tương ứng được lưu trong class.
3. **Accessor:** method công khai đọc component.

Chúng có quan hệ với nhau nhưng không phải cùng một thành viên. `javap -v` giúp nhìn thấy Record attribute bên cạnh field và method trong class file.

## 7. Đối chiếu canonical constructor bằng -c

Dùng:

~~~bash
javap -classpath out -p -c demo.Person
~~~

Trong phần constructor, có thể thấy bytecode thực hiện các thao tác tương ứng với mã nguồn:

- Gọi constructor của superclass `java.lang.Record`.
- Kiểm tra `name` không null.
- Gọi `strip()` để chuẩn hóa chuỗi.
- Kiểm tra tên không rỗng và tuổi không âm.
- Gán giá trị cuối cùng vào các field component bằng lệnh bytecode ghi field.

Các lệnh JVM thường gặp khi đọc constructor:

| Lệnh | Ý nghĩa khái quát |
| --- | --- |
| `aload_0` | Đưa tham chiếu `this` lên operand stack. |
| `aload_1`, `iload_2` | Nạp tham số hoặc local variable tương ứng. |
| `invokespecial` | Gọi constructor hoặc một số method đặc biệt. |
| `invokevirtual` | Gọi instance method. |
| `invokestatic` | Gọi static method. |
| `putfield` | Ghi field instance. |
| `getfield` | Đọc field instance. |
| `if...` | Nhảy có điều kiện. |
| `athrow` | Ném exception. |
| `return` | Kết thúc method void/constructor. |

Với compact canonical constructor, compiler bổ sung phép gán component sau phần thân constructor khi constructor hoàn tất bình thường. Do đó, khi đọc bytecode có thể thấy các lệnh `putfield` dù trong mã nguồn compact constructor không viết `this.name = name` hoặc `this.age = age`.

Không nên kết luận một chuỗi bytecode cụ thể là bắt buộc cho mọi JDK. Compiler có thể thay đổi cách sắp xếp lệnh, dùng local slot khác hoặc tối ưu hóa, miễn tuân thủ semantics của Java.

## 8. Đối chiếu accessor và method được sinh

Accessor mặc định của component thường đọc field tương ứng. Với `name()`, bytecode có thể có dạng khái quát:

~~~text
public java.lang.String name();
  Code:
     0: aload_0
     1: getfield      #...  // Field name:Ljava/lang/String;
     4: areturn
~~~

Accessor `age()` tương tự nhưng đọc field kiểu primitive `int`.

Nếu record tự khai báo accessor tường minh, `javap` sẽ hiển thị method đã biên dịch từ implementation đó. Vì vậy, chỉ nhìn thấy method `name()` trong output không đủ để khẳng định nó do compiler sinh; cần đối chiếu mã nguồn.

Các method `equals()`, `hashCode()` và `toString()` mặc định có thể dùng invokedynamic cùng bootstrap method dành cho record. Trong output verbose, có thể thấy `BootstrapMethods` và tham chiếu đến `java.lang.runtime.ObjectMethods.bootstrap`.

Đây là chi tiết triển khai class file của compiler/JDK. Khi học Java, cần nắm semantics: method mặc định của record dựa trên các component theo quy tắc record. Không viết code phụ thuộc vào số thứ tự constant pool, chỉ số bootstrap hoặc chuỗi bytecode cụ thể.

## 9. Phân biệt thành viên implicit và explicit

Bảng dưới đây dùng record `Person` ở đầu bài:

| Thành viên | Có khai báo trong source? | Có trong class file? | Ghi chú |
| --- | --- | --- | --- |
| Field `name` | Không khai báo riêng; component tạo ra | Có | Private final field tương ứng component. |
| Field `age` | Không khai báo riêng; component tạo ra | Có | Private final field tương ứng component. |
| Canonical constructor | Có dạng compact | Có | Compiler tạo constructor đầy đủ theo header. |
| Accessor `name()` | Không | Có | Compiler cung cấp vì không override. |
| Accessor `age()` | Không | Có | Compiler cung cấp vì không override. |
| `equals(Object)` | Không | Có | Method giá trị mặc định. |
| `hashCode()` | Không | Có | Method giá trị mặc định. |
| `toString()` | Không | Có | Method giá trị mặc định. |
| `isAdult()` | Có | Có | Method do người viết khai báo. |
| `ADULT_AGE` | Có | Có | Field static final do người viết khai báo. |
| Record attribute | Không viết trực tiếp | Có | Metadata component trong class file. |

Nếu record tự override `equals`, `hashCode` hoặc `toString`, class file sẽ chứa implementation tương ứng với mã nguồn. Nếu tự viết accessor, method accessor cũng xuất hiện nhưng bytecode phản ánh implementation tùy chỉnh.

## 10. Kiểm tra record lồng hoặc generic record

`javap` cũng dùng được với nested record. Ví dụ:

~~~java
package demo;

public class Order {
    public record Line(String sku, int quantity) {}
}
~~~

Biên dịch:

~~~bash
javac --release 16 -d out src/demo/Order.java
~~~

Tên binary của nested record dùng dấu `$`:

~~~bash
javap -classpath out -p -v 'demo.Order$Line'
~~~

Đặt tên class trong dấu nháy đơn để ký tự `$` không bị shell diễn giải như biến:

~~~powershell
javap -classpath out -p -v 'demo.Order$Line'
~~~

Generic record cũng có thể được kiểm tra:

~~~java
package demo;

public record Box<T>(T value) {}
~~~

Chạy:

~~~bash
javac --release 16 -d out src/demo/Box.java
javap -classpath out -p -v demo.Box
~~~

Trong class file, descriptor field có thể phản ánh kiểu đã erasure; phần `Signature` lưu generic signature khi có. Vì vậy, khi kiểm tra generic record, hãy phân biệt descriptor dùng ở cấp JVM với generic Signature attribute dành cho metadata kiểu tổng quát.

## 11. Quy trình kiểm tra thực tế

Khi cần xác minh một record trong dự án, có thể đi theo trình tự:

1. Xác định file nguồn record và package.
2. Biên dịch bằng JDK phù hợp với phiên bản source/target dự án.
3. Xác định thư mục chứa class file đã biên dịch.
4. Dùng `javap -p` để xem danh sách field, constructor và method.
5. Dùng `javap -s` để xem descriptor.
6. Dùng `javap -v` để kiểm tra Record attribute, flags và generic Signature.
7. Dùng `javap -c` để đọc bytecode của constructor, accessor hoặc method cần phân tích.
8. Đối chiếu output với source và JLS; không xem chi tiết bytecode là cam kết API.

Các lệnh mẫu:

~~~bash
javac --release 16 -d out src/demo/Person.java
javap -classpath out -p demo.Person
javap -classpath out -p -s demo.Person
javap -classpath out -p -c demo.Person
javap -classpath out -p -v demo.Person
~~~

Trong dự án Maven hoặc Gradle, class file thường nằm trong thư mục build output của dự án. Chỉ cần trỏ `-classpath` đến thư mục gốc chứa package tương ứng; không cần chạy một quy trình build mới nếu class file đã có và đúng phiên bản.

## 12. Những giới hạn và lỗi thường gặp

1. **Chạy javap trên file source:** `javap` kiểm tra class file; trước tiên phải biên dịch source thành `.class`.
2. **Quên package khi gọi class:** dùng tên đầy đủ như `demo.Person` và trỏ đúng `-classpath`.
3. **Không dùng `-p`:** field private có thể không hiện trong danh sách mặc định; thêm `-p` để xem.
4. **Chỉ dùng `-c` rồi tìm Record attribute:** bytecode disassembly không thay thế phần metadata verbose; dùng `-v` để xem Record attribute.
5. **Nhầm component với field:** component có metadata riêng trong Record attribute, đồng thời có field và accessor tương ứng.
6. **Cho rằng mọi method xuất hiện đều do compiler sinh:** method người viết cũng có trong class file; đối chiếu mã nguồn để phân loại.
7. **Phụ thuộc bytecode cụ thể của equals/hashCode/toString:** compiler có thể dùng invokedynamic/ObjectMethods hoặc cách triển khai khác phù hợp đặc tả.
8. **Nhầm descriptor với generic type:** descriptor phản ánh kiểu JVM sau erasure; xem thêm Signature attribute khi kiểm tra generic.
9. **Dùng javap từ JDK không phù hợp:** dùng công cụ có khả năng đọc class file của phiên bản đang kiểm tra.
10. **Coi output javap là hợp đồng ngôn ngữ:** dùng JLS và Java API để xác định semantics; javap chỉ là công cụ quan sát artifact đã biên dịch.

## 13. Bài tập thực hành

1. Biên dịch record `Person(String name, int age)` bằng `javac --release 16`. Dùng `javap -p` để liệt kê field và method.
2. Dùng `javap -v` và tìm `Record` attribute. Ghi lại tên, kiểu và thứ tự component.
3. Dùng `javap -s` để ghi descriptor của constructor và hai accessor.
4. Dùng `javap -c` để tìm các lệnh `putfield` trong canonical constructor. Giải thích chúng liên quan đến component nào.
5. Thêm một instance method vào record, biên dịch lại và đối chiếu method mới trong output.
6. Tự khai báo accessor cho một component, sau đó dùng `javap -c` để xem implementation đã biên dịch.
7. Khai báo generic record `Box<T>(T value)`. So sánh descriptor và Signature attribute.
8. Khai báo nested record `Order.Line` và tìm class file tương ứng bằng tên binary có dấu `$`.
9. Giải thích vì sao thứ tự bytecode hoặc chỉ số constant pool không nên được dùng làm cam kết tương thích giữa các JDK.

## Ghi nhớ

`javap` là công cụ JDK để kiểm tra class file sau khi biên dịch. Dùng `-p` để xem cả thành viên private, `-s` để xem descriptor, `-c` để disassemble bytecode và `-v` để đọc metadata chi tiết. Với record, `Record` attribute cho thấy component metadata; field private final, canonical constructor và accessor cho thấy cấu trúc được ánh xạ vào class file; `equals`, `hashCode` và `toString` mặc định cũng xuất hiện dù không viết trực tiếp trong source. Hãy đối chiếu class file với mã nguồn và JLS để phân biệt thành viên implicit với explicit. Descriptor, constant pool và bytecode giúp hiểu cách compiler biểu diễn record, nhưng chi tiết triển khai có thể thay đổi giữa các JDK; semantics của record mới là hợp đồng cần dựa vào.

**Tài liệu tham khảo chính thức:**

- [Java Development Kit Tools Specification – javap](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javap.html)
- [Java Language Specification – Record Classes, mục 8.10](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-8.html#jls-8.10)
- [Java Virtual Machine Specification – The Record Attribute](https://docs.oracle.com/en/java/javase/26/docs/specs/jvms/jvms-4.html#jvms-4.7.30)
- [Java Virtual Machine Specification – Descriptors, mục 4.3](https://docs.oracle.com/en/java/javase/26/docs/specs/jvms/jvms-4.html#jvms-4.3)
