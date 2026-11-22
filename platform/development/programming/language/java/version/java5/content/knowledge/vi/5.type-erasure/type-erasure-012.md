# Phân biệt thông tin kiểu của đối tượng với chữ ký generic được lưu trong class file

## 1. Xóa kiểu không đồng nghĩa mọi dấu vết generic đều biến mất

Hai nhận định sau cùng đúng:

- Đối tượng `new ArrayList<String>()` và `new ArrayList<Integer>()` có cùng lớp thực thi `ArrayList`.
- Reflection vẫn có thể đọc được khai báo một trường là `List<String>` hoặc một lớp con kế thừa `Holder<String>`.

Chúng không mâu thuẫn vì đang nói về những nguồn thông tin khác nhau:

1. **Lớp thực tế của đối tượng:** đối tượng thuộc lớp nào khi chạy.
2. **Descriptor trong class file:** mô tả kiểu của trường/phương thức theo dạng JVM dùng sau xóa kiểu.
3. **Metadata generic của khai báo:** thông tin như `List<String>`, `List<T>` hoặc `Holder<String>` được lưu để phản ánh cấu trúc khai báo.

Đừng gộp cả ba thành một câu hỏi “Java còn biết kiểu không?”. Cần hỏi rõ đang biết kiểu của đối tượng, kiểu đã xóa phục vụ thực thi hay kiểu mà tác giả đã khai báo.

Thuộc tính `Signature` của class file được mô tả trong [JVMS §4.7.9](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-4.html#jvms-4.7.9). Cơ chế này vẫn được sử dụng trong Java hiện đại; ví dụ trong bài tương thích Java 17 trở lên.

## 2. Lớp thực tế không ghi một đối số kiểu riêng cho từng đối tượng

Xét các khai báo minh họa:

```java
List<String> names = new ArrayList<>();
List<Integer> numbers = new ArrayList<>();

System.out.println(names.getClass().equals(numbers.getClass())); // true
```

`getClass()` trả về lớp thực tế của đối tượng, không trả một biểu diễn `ArrayList<String>` hay `ArrayList<Integer>` riêng cho từng đối tượng.

Tương tự:

```java
class Holder<T> {
}
```

Hai đối tượng `new Holder<String>()` và `new Holder<Integer>()` cùng có lớp thực thi `Holder`. Nếu hỏi lớp đó đã khai báo tham số kiểu nào bằng `getTypeParameters()`, kết quả cho biết tham số `T` của **khai báo lớp**, không phải đối số `String` hoặc `Integer` của một biến tại nơi gọi.

Kiểu tĩnh của biến vẫn rất quan trọng khi biên dịch. Ví dụ `Holder<String>` giúp kiểm tra những thao tác dùng `T` như `String`. Nhưng đối tượng thông thường không tự mang một trường metadata bí mật ghi lại rằng lần khởi tạo này đã dùng `String`.

Ngoài ra, các giá trị được lưu bên trong vẫn có lớp thực tế riêng. Một phần tử đang là `String` vẫn thuộc lớp `String`; điều bị mất ở đây là nhãn đối số kiểu của đối tượng chứa thông thường, không phải lớp của mọi phần tử.

## 3. Descriptor và thuộc tính `Signature` phục vụ hai vai trò khác nhau

Ví dụ một trường:

```java
public List<String> labels;
```

Trong class file, có thể đồng thời thấy:

```text
descriptor: Ljava/util/List;
Signature: Ljava/util/List<Ljava/lang/String;>;
```

Descriptor mô tả trường có kiểu `List` sau xóa kiểu. Thuộc tính `Signature` bổ sung rằng kiểu được khai báo là `List<String>`.

Với tham số kiểu của lớp:

```java
class Holder<T> {
    public List<T> values;

    public T echo(T value) {
        return value;
    }
}
```

Có những dạng tương ứng sau:

| Khai báo | Descriptor | Generic `Signature` |
| --- | --- | --- |
| `List<T> values` | `Ljava/util/List;` | `Ljava/util/List<TT;>;` |
| `T echo(T value)` | `(Ljava/lang/Object;)Ljava/lang/Object;` | `(TT;)TT;` |

`TT;` trong cú pháp chữ ký class file biểu diễn biến kiểu có tên `T`. Cận ngầm định của `T` là `Object`, nên descriptor của `echo` nhận và trả `Object`.

JVM không dùng chuỗi metadata `List<String>` để tự duyệt và kiểm tra mọi phần tử trong trường `labels`. Descriptor cùng mã lệnh thực thi có vai trò khác với thông tin khai báo mà reflection có thể đọc.

Cũng cần phân biệt tên thuộc tính `Signature` trong class file với thuật ngữ chữ ký phương thức của ngôn ngữ Java. Khi đọc công cụ, hãy xác định nó đang hiển thị descriptor hay metadata generic để tránh suy luận sai về overload, liên kết phương thức hoặc kiểm tra lúc chạy.

## 4. Reflection có cặp API cho kiểu đã xóa và kiểu generic

Các cặp thường gặp:

| Câu hỏi về khai báo | API cho kiểu lớp/kiểu đã xóa | API cho metadata generic |
| --- | --- | --- |
| Kiểu của trường | `Field.getType()` | `Field.getGenericType()` |
| Kiểu trả về phương thức | `Method.getReturnType()` | `Method.getGenericReturnType()` |
| Các kiểu tham số phương thức | `Method.getParameterTypes()` | `Method.getGenericParameterTypes()` |
| Lớp cha trực tiếp | `Class.getSuperclass()` | `Class.getGenericSuperclass()` |
| Các interface được khai báo | `Class.getInterfaces()` | `Class.getGenericInterfaces()` |

Ví dụ, [Field.getGenericType](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/Field.html#getGenericType()) phản ánh **kiểu đã khai báo của trường**. Nó không đọc giá trị hiện tại rồi suy ra đối số kiểu từ nội dung của giá trị.

Một trường `List<String> labels` có thể đang là `null`, rỗng hoặc chứa các chuỗi. Metadata `List<String>` của trường không thay đổi theo những trạng thái dữ liệu đó.

Ngược lại, `labels.getClass()` chỉ có ý nghĩa khi giá trị trường khác `null`, và cho biết lớp triển khai của đối tượng hiện tại, chẳng hạn `ArrayList`. Hai API đang trả lời hai câu hỏi khác nhau.

## 5. `Type` không phải lúc nào cũng là một `Class`

Các API generic thường trả `java.lang.reflect.Type`. Cần kiểm tra dạng thông tin thay vì ép mọi kết quả về `Class<?>`.

| Dạng `Type` | Ví dụ ý nghĩa |
| --- | --- |
| `Class<?>` | Một lớp/kiểu được biểu diễn trực tiếp, như `String` |
| `ParameterizedType` | Một kiểu tham số hóa như `List<String>` hoặc `Holder<String>` |
| `TypeVariable<?>` | Một biến kiểu được khai báo, như `T` |
| `WildcardType` | Một wildcard như `? extends Number` |
| `GenericArrayType` | Một kiểu mảng có thành phần generic phù hợp, như `T[]` |

Ví dụ xử lý an toàn dạng tham số hóa:

```java
Type type = field.getGenericType();
if (type instanceof ParameterizedType parameterized) {
    Type[] arguments = parameterized.getActualTypeArguments();
    for (Type argument : arguments) {
        System.out.println(argument.getTypeName());
    }
}
```

Đây là đoạn rời cần có biến `field` và import reflection tương ứng khi đặt vào chương trình.

Tên `getActualTypeArguments()` dễ gây hiểu nhầm. Từ “actual” ở đây nói về các đối số kiểu của **biểu diễn kiểu tham số hóa đó**, không có nghĩa phương thức đã nhìn vào một đối tượng sống để tìm kiểu của mọi phần tử. Các đối số trả về vẫn có thể là biến kiểu hoặc wildcard, không nhất thiết là những `Class` cụ thể.

Hợp đồng này được mô tả trong [ParameterizedType](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/ParameterizedType.html).

## 6. Vì sao lớp con lại có thể giữ `String`?

Giả sử:

```java
class Holder<T> {
}

class StringHolder extends Holder<String> {
}
```

Trong **khai báo lớp con**, tác giả đã ghi rõ lớp cha là `Holder<String>`. Class file của `StringHolder` có thể lưu quan hệ đó trong `Signature`.

Vì vậy, `StringHolder.class.getGenericSuperclass()` có thể trả một `ParameterizedType` có đối số là `String`. Đây là thông tin về cạnh kế thừa được khai báo, không phải nhãn tự động sinh cho từng đối tượng `new Holder<String>()`.

Một lớp con ẩn danh cũng có thể tạo một khai báo tương tự:

```java
Holder<String> anonymous = new Holder<String>() {};
Type parent = anonymous.getClass().getGenericSuperclass();
```

Dấu `{}` tạo một lớp con ẩn danh; class file của lớp mới có thể ghi lớp cha tham số hóa là `Holder<String>`. Đây là nền tảng của một số kỹ thuật lưu mô tả kiểu qua lớp con.

Điểm cần giữ:

- `new Holder<String>()` tạo đối tượng trực tiếp của lớp `Holder`.
- `new Holder<String>() {}` tạo đối tượng của một lớp con mới, có khai báo lớp cha mang `String`.

Nếu viết một lớp con với đối số vẫn là biến kiểu `T` trong ngữ cảnh generic, metadata có thể chỉ giữ `T`, không tự giải quyết nó thành đối số của mọi lần gọi phương thức. Kỹ thuật lớp con chỉ giữ được thông tin có trong khai báo mà trình biên dịch thực sự ghi lại.

Tài liệu [Class.getGenericSuperclass](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Class.html#getGenericSuperclass()) mô tả việc đọc kiểu cha trực tiếp, không hứa khôi phục mọi đối số kiểu bị xóa từ một đối tượng tùy ý.

## 7. Metadata ở lớp cha không tự được thay thế trong mọi đối tượng reflection

Với `Holder<T>` có phương thức `T echo(T value)`, đọc phương thức được khai báo trên `Holder` trả thông tin generic là `T`.

Ngay cả khi tìm phương thức public được kế thừa qua `StringHolder.class.getMethod(...)`, đối tượng `Method` vẫn đại diện phương thức có nguồn khai báo ở `Holder`. `getGenericReturnType()` vẫn có thể trả `T`, không tự biến thành `String`.

Để suy ra kiểu trong ngữ cảnh `StringHolder`, công cụ phải kết hợp:

```text
StringHolder extends Holder<String>
                ↓
ánh xạ T của Holder thành String
                ↓
áp dụng ánh xạ vào kiểu T của echo
```

Khi có nhiều tầng kế thừa, biến kiểu lồng nhau hoặc interface, việc giải quyết cần theo đúng đường khai báo và ánh xạ tương ứng. Không nên chỉ đọc tên `T` rồi cho rằng đó là một tham số chung không cần biết lớp/phương thức nào đã khai báo nó.

Đây là lý do các công cụ xử lý kiểu generic cần ngữ cảnh khai báo. Reflection cung cấp những mảnh thông tin; không phải mọi API đều tự tính ra một kiểu cụ thể cuối cùng cho mọi cách nhìn phương thức.

## 8. Chương trình hoàn chỉnh

Lưu vào `GenericMetadataDemo.java`, dùng Java 17 trở lên:

```java
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.Type;
import java.util.ArrayList;
import java.util.List;

public class GenericMetadataDemo {
    static class Holder<T> {
        public List<T> values = new ArrayList<>();
        public List<String> labels = new ArrayList<>(List.of("label"));

        public T echo(T value) {
            return value;
        }
    }

    static final class StringHolder extends Holder<String> {
    }

    static List<String> declaredNames() {
        return List.of("Java");
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        Holder<String> strings = new Holder<>();
        Holder<Integer> integers = new Holder<>();
        System.out.println("same Holder class = " + strings.getClass().equals(integers.getClass()));
        System.out.println("declared class parameter = " + strings.getClass().getTypeParameters()[0].getTypeName());

        Field values = Holder.class.getDeclaredField("values");
        Field labels = Holder.class.getDeclaredField("labels");
        System.out.println("values erased = " + values.getType().getTypeName());
        System.out.println("values generic = " + values.getGenericType().getTypeName());
        System.out.println("labels generic = " + labels.getGenericType().getTypeName());
        System.out.println("labels object class = " + strings.labels.getClass().getTypeName());

        Method echo = Holder.class.getDeclaredMethod("echo", Object.class);
        System.out.println("echo erased return = " + echo.getReturnType().getTypeName());
        System.out.println("echo generic return = " + echo.getGenericReturnType().getTypeName());

        Method names = GenericMetadataDemo.class.getDeclaredMethod("declaredNames");
        System.out.println("names erased return = " + names.getReturnType().getTypeName());
        System.out.println("names generic return = " + names.getGenericReturnType().getTypeName());

        Type parent = StringHolder.class.getGenericSuperclass();
        if (parent instanceof ParameterizedType parameterized) {
            System.out.println("subclass argument = " + parameterized.getActualTypeArguments()[0].getTypeName());
        }
        Method inherited = StringHolder.class.getMethod("echo", Object.class);
        System.out.println("inherited generic return = " + inherited.getGenericReturnType().getTypeName());

        Holder<String> anonymous = new Holder<String>() {};
        Type anonymousParent = anonymous.getClass().getGenericSuperclass();
        if (anonymousParent instanceof ParameterizedType parameterized) {
            System.out.println("anonymous subclass argument = " + parameterized.getActualTypeArguments()[0].getTypeName());
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -Xlint:unchecked -encoding UTF-8 GenericMetadataDemo.java
java GenericMetadataDemo
```

Kết quả chuẩn:

```text
same Holder class = true
declared class parameter = T
values erased = java.util.List
values generic = java.util.List<T>
labels generic = java.util.List<java.lang.String>
labels object class = java.util.ArrayList
echo erased return = java.lang.Object
echo generic return = T
names erased return = java.util.List
names generic return = java.util.List<java.lang.String>
subclass argument = java.lang.String
inherited generic return = T
anonymous subclass argument = java.lang.String
```

Đọc kết quả theo ba nhóm:

1. `same Holder class` và tham số `T` cho thấy lớp của đối tượng không tự lưu đối số của biến `strings` hay `integers`.
2. Các dòng trường và phương thức cho thấy cùng một khai báo có thể được nhìn qua kiểu đã xóa hoặc metadata generic.
3. Hai trường hợp lớp con cho thấy thông tin `String` được giữ ở khai báo kế thừa. Dòng `inherited generic return = T` nhắc rằng vẫn cần ánh xạ ngữ cảnh khi suy luận kiểu của thành viên kế thừa.

Không có cast unchecked trong chương trình. Việc dùng `instanceof ParameterizedType` là kiểm tra dạng đối tượng metadata reflection, không phải kiểm tra kiểu phần tử của một danh sách dữ liệu.

## 9. Xem trực tiếp bằng `javap`

Sau khi biên dịch, dùng PowerShell:

```powershell
javap -v -p 'GenericMetadataDemo$Holder'
javap -v -p 'GenericMetadataDemo$StringHolder'
```

Dấu nháy đơn giữ nguyên ký tự `$` trong tên lớp lồng. `-v` hiển thị metadata chi tiết; `-p` hiển thị cả các thành viên không public.

Các thông tin chính trên `Holder`, bỏ qua chỉ số constant pool:

```text
values:
  descriptor: Ljava/util/List;
  Signature: Ljava/util/List<TT;>;

labels:
  descriptor: Ljava/util/List;
  Signature: Ljava/util/List<Ljava/lang/String;>;

echo:
  descriptor: (Ljava/lang/Object;)Ljava/lang/Object;
  Signature: (TT;)TT;
```

Class signature của `Holder` có dạng:

```text
<T:Ljava/lang/Object;>Ljava/lang/Object;
```

Nó mô tả một tham số kiểu `T` có cận `Object`, cùng lớp cha `Object`.

Còn `StringHolder` có class signature dạng:

```text
LGenericMetadataDemo$Holder<Ljava/lang/String;>;
```

Chuỗi này thuộc class file của lớp con. Nó không tạo hai lớp thực thi riêng cho mọi `Holder<String>` và `Holder<Integer>` thông thường.

Các trích đoạn trên được rút gọn để so sánh ý nghĩa; tên nhãn, định dạng trình bày và chỉ số constant pool trong đầu ra đầy đủ có thể khác theo công cụ hoặc phiên bản biên dịch.

## 10. Những giới hạn cần tính tới khi dùng metadata

**Metadata mô tả hợp đồng khai báo, không xác thực nội dung.** Đọc được `List<String>` của một trường không tương đương duyệt và kiểm tra từng phần tử đang được lưu. Nếu an toàn kiểu đã bị phá vỡ bằng một đường ghi không kiểm tra, metadata không tự sửa giá trị sai.

**Biến cục bộ không trở thành metadata của đối tượng.** Khai báo `Holder<String> value` trong một phương thức không làm `value.getClass()` trả một lớp có nhãn `String`. Thông tin debug về biến cục bộ, nếu được tạo, cũng là dữ liệu về vị trí trong phương thức, không phải nhãn đối số kiểu gắn với từng đối tượng.

**Có metadata không có nghĩa mọi đối số đã cụ thể.** `List<T>`, wildcard và cấu trúc generic lồng nhau có thể cần nhiều bước giải quyết. Một `Type` không bảo đảm ép được thành `Class<?>`.

**Cần biết class file thực tế đang được đọc.** Công cụ biến đổi hoặc đóng gói bytecode có thể xử lý metadata; nếu ứng dụng phụ thuộc generic reflection, phải kiểm tra các thuộc tính cần thiết vẫn được giữ trong sản phẩm tạo ra. Đừng suy ra từ mã nguồn rằng mọi artifact đã qua biến đổi đều có cùng thông tin.

**Không suy luận bằng dữ liệu mẫu.** Một danh sách hiện chỉ có chuỗi không chứng minh khai báo gốc là `List<String>`; nó có thể được khai báo là `List<Object>`. Ngược lại, danh sách rỗng không làm biến mất metadata của trường có khai báo `List<String>`.

## 11. Tự kiểm tra

**Câu 1.** Vì sao `getClass()` của hai đối tượng `Holder<String>` và `Holder<Integer>` bằng nhau nhưng `Field.getGenericType()` vẫn đọc được `List<String>` ở một trường?

Hai API đọc hai nguồn khác nhau: lớp thực tế chung của đối tượng và metadata của một khai báo trường cụ thể.

**Câu 2.** `getActualTypeArguments()` có luôn trả `Class` không?

Không. Nó trả các `Type`, có thể là lớp, biến kiểu, wildcard hoặc cấu trúc tham số hóa khác. Cần kiểm tra dạng thông tin.

**Câu 3.** `StringHolder extends Holder<String>` có làm mọi đối tượng `Holder<String>` lưu đối số kiểu lúc chạy không?

Không. Nó lưu một quan hệ generic ở khai báo lớp con `StringHolder`. Các đối tượng được tạo trực tiếp từ `Holder` vẫn thuộc lớp chung `Holder`.

**Câu 4.** Vì sao phương thức `echo` tìm qua lớp con vẫn báo kiểu trả về generic là `T`?

Vì đối tượng reflection đại diện phương thức được khai báo ở `Holder<T>`. Muốn hiểu nó trong ngữ cảnh lớp con, cần kết hợp ánh xạ `T → String` từ quan hệ kế thừa.
