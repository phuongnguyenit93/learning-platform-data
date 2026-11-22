# Kiểu reifiable và thông tin kiểu có thể kiểm tra lúc chạy

## 1. Sau xóa kiểu, thông tin nào còn đủ để kiểm tra?

Java có thể kiểm tra một đối tượng có phải `String` hoặc một mảng có phải `String[]` khi chạy. Nhưng từ một biến kiểu `Object`, Java không thể kiểm tra đầy đủ rằng đối tượng là `List<String>` chỉ bằng việc xem lớp thực tế của nó.

Nguyên nhân là kiểu phần tử generic như `String` trong `List<String>` không được gắn thành một nhãn riêng trên từng đối tượng danh sách thông thường. Sau xóa kiểu, các đối tượng `ArrayList<String>` và `ArrayList<Integer>` vẫn thuộc cùng lớp thực thi `ArrayList`.

**Kiểu reifiable** là thuật ngữ của Java chỉ kiểu có thông tin đầy đủ tương ứng còn khả dụng lúc chạy. Có thể hiểu là “kiểu còn đủ thông tin để nhận diện lúc chạy”, nhưng nên giữ từ reifiable để đọc tài liệu và thông báo lỗi.

Điều quan trọng là xét **toàn bộ kiểu được nêu**. Java biết một đối tượng thuộc lớp `ArrayList`; điều đó không đồng nghĩa Java tự biết đối số kiểu của danh sách là `String`.

Định nghĩa chính thức nằm trong [JLS §4.7 về reifiable types](https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.7). Bài áp dụng cho Java hiện đại; các ví dụ chạy được từ Java 17.

## 2. Phân loại những dạng thường dùng

| Kiểu | Reifiable? | Lý do |
| --- | --- | --- |
| `int`, `boolean` | Có | Kiểu nguyên thủy vẫn được biểu diễn đầy đủ |
| `String`, `Number` | Có | Kiểu lớp không generic |
| `List<?>` | Có | Mọi đối số kiểu đều là wildcard không giới hạn |
| `Map<?, ?>` | Có | Cả hai đối số kiểu đều không yêu cầu biết kiểu cụ thể |
| `List<String>` | Không | Đối số kiểu `String` của danh sách bị xóa |
| `List<Object>` | Không | `Object` vẫn là một đối số kiểu cụ thể cần được biểu đạt |
| `List<? extends Number>` | Không | Wildcard có cận không phải wildcard không giới hạn |
| `Map<String, ?>` | Không | Vẫn còn yêu cầu cụ thể đối với kiểu khóa |
| `T` trong một khai báo generic | Không | `T` không có một danh tính kiểu cụ thể riêng lúc chạy |
| `String[]`, `int[]`, `List<?>[]` | Có | Kiểu thành phần của mảng là reifiable |
| `List<String>[]` | Không | Kiểu thành phần `List<String>` không reifiable |

Với kiểu lồng nhau, phải xét các phần kiểu bao ngoài và kiểu thành viên theo quy tắc của đặc tả. Một phần tham số hóa không reifiable có thể làm cả kiểu lồng không reifiable. Kiểu giao (intersection type) cũng không reifiable.

Bảng tập trung vào các dạng dùng trong mã generic hiện đại, không phải danh sách mọi trường hợp được đặc tả phân loại.

### Vì sao `List<?>` lại reifiable?

`List<?>` chỉ yêu cầu biết đối tượng là một `List` với kiểu phần tử chưa xác định. Nó không yêu cầu kiểm tra các phần tử là chuỗi, số hoặc một kiểu cụ thể khác.

Do đó, kiểm tra một đối tượng là `List<?>` không mất đi điều kiện về đối số kiểu cần kiểm chứng: dấu `?` không đặt ra điều kiện cụ thể đó ngay từ đầu.

Ngược lại, `List<Object>` không có nghĩa “một danh sách bất kỳ”. Nó biểu đạt danh sách có kiểu phần tử được khai báo là `Object`, cho phép ghi các kiểu tham chiếu khác nhau qua tham chiếu này. Đó là hợp đồng khác với một danh sách chuỗi được nhìn dưới dạng `List<?>`.

## 3. Kiểm tra một `Object` bằng `instanceof`

Đoạn sau hợp lệ và không cần ép kiểu không kiểm tra:

```java
Object candidate = List.of("Java", "Spring");

if (candidate instanceof List<?> values) {
    System.out.println(values.size());
    Object first = values.get(0);
}
```

Khi điều kiện đúng, `values` được dùng như `List<?>`. Có thể đọc phần tử dưới dạng `Object`, nhưng không được kết luận từng phần tử là `String`.

Đoạn minh họa bị từ chối:

```java
Object candidate = List.of("Java");
// if (candidate instanceof List<String> values) { } // Lỗi biên dịch.
```

Từ một `Object` bất kỳ, JVM không có đủ thông tin để kiểm tra hợp đồng `List<String>` của mọi phần tử bằng phép kiểm tra kiểu đó. Một danh sách số nguyên cũng có thể có cùng lớp thực tế với danh sách chuỗi.

Nếu đối tượng là `null`, phép kiểm tra `instanceof` cho kết quả `false`. Nó không ném ngoại lệ chỉ vì toán hạng là `null`.

## 4. Quy tắc hiện đại: không cấm mọi `instanceof` có đối số kiểu cụ thể

Không nên rút gọn thành quy tắc “mọi `instanceof List<String>` hoặc `instanceof ArrayList<String>` đều bị cấm”. Tính hợp lệ còn phụ thuộc **kiểu tĩnh của biểu thức bên trái** và khả năng kiểm tra phép thu hẹp kiểu mà không cần phép chuyển đổi unchecked.

Ví dụ này hợp lệ trên Java 17 trở lên:

```java
List<String> values = new ArrayList<>(List.of("Java"));

if (values instanceof ArrayList<String> array) {
    System.out.println(array.size());
}
```

Ở đây, `values` đã có hợp đồng tĩnh `List<String>`. Phép kiểm tra cần xác định đối tượng có thuộc lớp triển khai `ArrayList` hay không; ràng buộc phần tử `String` được giữ từ thông tin tĩnh đã có. JVM không duyệt danh sách để chứng minh kiểu của từng phần tử.

Vì thế, hai điều sau cùng đúng:

- `ArrayList<String>` là kiểu không reifiable.
- Một phép kiểm tra `instanceof ArrayList<String>` cụ thể vẫn có thể hợp lệ khi thông tin tĩnh cho phép kiểm tra mà không cần một phép chuyển đổi unchecked.

Quy tắc này được [JLS §15.20.2](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.20.2) nêu rõ. Khi xem ví dụ, luôn đọc cả khai báo của toán hạng bên trái; không chỉ nhìn phần sau từ khóa `instanceof`.

Đừng dùng trường hợp hợp lệ này để suy ra có thể kiểm tra `Object → List<String>` tùy ý. Hai trường hợp có thông tin tĩnh ban đầu khác nhau.

## 5. Mảng giữ kiểu thành phần lúc chạy

Mảng Java ghi nhận kiểu thành phần thực tế. Vì vậy:

```java
String[] texts = new String[2];
Object[] alias = texts;

// alias[0] = 10; // Biên dịch được, nhưng ném ArrayStoreException khi chạy.
```

Mặc dù `alias` có kiểu tĩnh `Object[]`, đối tượng mảng thật vẫn là `String[]`. JVM kiểm tra việc ghi phần tử và từ chối một `Integer` không phù hợp.

Điều này giải thích vì sao tạo mảng với kiểu thành phần generic không reifiable bị hạn chế:

```java
// List<String>[] names = new List<String>[2]; // Lỗi: generic array creation.
List<?>[] lists = new List<?>[2];               // Hợp lệ.
```

Đối với `List<?>[]`, yêu cầu của mảng là mỗi phần tử phải là một `List` hoặc `null`; không có lời hứa rằng mọi danh sách con đều chứa chuỗi. Vì vậy có thể viết:

```java
lists[0] = List.of("A");
lists[1] = List.of(1);
```

Mảng vẫn kiểm tra được một phần tử mới có phải `List` hay không, nhưng không kiểm tra đối số kiểu của từng danh sách con.

Cũng cần phân biệt **khai báo một biến có kiểu mảng** với **tạo đối tượng mảng**. Khai báo `List<String>[] values;` có thể xuất hiện trong mã; điều bị cấm ở ví dụ trên là biểu thức tạo `new List<String>[2]`. Đừng giải quyết bằng cách tạo mảng rồi ép kiểu unchecked để giả lập một bảo đảm mà JVM không thể kiểm tra.

Quy tắc tạo mảng được mô tả trong [JLS §15.10.1](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.10.1). Khi cần một cấu trúc chứa nhiều danh sách chuỗi, `List<List<String>>` thường dễ giữ an toàn kiểu hơn việc cố tạo mảng generic.

## 6. Class literal và `Class<T>` kiểm tra được gì?

Các class literal sau hợp lệ:

```java
Class<String> stringType = String.class;
Class<?> listType = List.class;
Class<?> arrayType = String[].class;
```

Không có class literal riêng cho các đối số kiểu generic:

```java
// List<String>.class  // Không hợp lệ.
// List<?>.class       // Cũng không phải cú pháp class literal hợp lệ.
// T.class             // Không hợp lệ với tham số kiểu T.
```

`List<?>` reifiable không có nghĩa mọi cấu trúc cú pháp nhận kiểu đều chấp nhận nó dưới cùng một hình thức. Class literal có quy tắc cú pháp riêng; dùng `List.class` để lấy đối tượng lớp của `List`.

Có thể dùng token lớp cho kiểm tra kiểu cụ thể:

```java
static <T> T checkedValue(Object value, Class<T> type) {
    return type.cast(value);
}
```

Ví dụ `checkedValue("Java", String.class)` trả `String` sau kiểm tra phù hợp. Nhưng `List.class.isInstance(candidate)` chỉ kiểm tra đối tượng là một `List`; nó không chứng minh các phần tử là `String`.

Với `T extends Number`, cận `Number` cho phép một số thao tác khi biên dịch; nó không tự tạo một token lớp đại diện chính xác cho `T`. Nếu cần kiểm tra một kiểu cụ thể lúc chạy, API phải nhận hoặc có cách cung cấp thông tin tương ứng một cách tường minh.

Một kiểu không reifiable vẫn có thể có phần thông tin kiểm tra được, như lớp sau xóa kiểu. “Không reifiable” không có nghĩa đối tượng hoàn toàn không có lớp hay không có thông tin kiểu nào.

## 7. Metadata generic qua reflection khác kiểu thực tế của từng đối tượng

Một phương thức có thể khai báo:

```java
static List<String> declaredNames() {
    return List.of("Java");
}
```

Reflection có thể đọc kiểu trả về khai báo là `List<String>` qua `Method.getGenericReturnType()`, trong khi `getReturnType()` trả lớp sau xóa kiểu là `List`.

Điều này không mâu thuẫn với xóa kiểu. Class file có thể giữ metadata mô tả **khai báo** generic để reflection và công cụ sử dụng. Metadata đó không biến mỗi đối tượng danh sách thành một thực thể mang nhãn kiểu phần tử có thể kiểm tra tự động.

Cần phân biệt:

| Thông tin | Ví dụ | Điều nó cho biết |
| --- | --- | --- |
| Lớp thực tế của đối tượng | `values.getClass()` | Đối tượng thuộc lớp triển khai nào |
| Kiểu generic trong khai báo | `method.getGenericReturnType()` | Tác giả phương thức khai báo kết quả theo kiểu gì |
| Giá trị phần tử hiện có | Duyệt rồi kiểm tra `instanceof String` | Các giá trị đang quan sát có phù hợp điều kiện cụ thể không |

`Type` và `ParameterizedType` là những mô hình metadata; chúng không phải phép quét và xác thực tự động mọi phần tử trong một danh sách. Một số khai báo lớp con cũng có thể giữ quan hệ generic ở superclass hoặc interface, nhưng không thể dựa vào đó để suy ra tùy ý đối số kiểu của mọi đối tượng generic.

Hợp đồng của [Method.getGenericReturnType](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/Method.html#getGenericReturnType()) nói về kiểu trả về của phương thức được phản chiếu, không phải việc xác thực nội dung của một đối tượng bất kỳ.

## 8. Nếu thật sự cần một danh sách chuỗi tại ranh giới dữ liệu

Khi nhận `Object` từ một nguồn chưa có hợp đồng kiểu đáng tin, có thể:

1. Kiểm tra nó là `List<?>`.
2. Duyệt từng giá trị và kiểm tra điều kiện nghiệp vụ.
3. Tạo một bản sao có kiểu rõ ràng từ những giá trị đã kiểm tra.

Ví dụ trong chương trình tiếp theo từ chối cả phần tử khác chuỗi lẫn `null`, rồi trả `List<String>` không cho sửa. Danh sách rỗng được chấp nhận vì không có phần tử vi phạm.

Đây là xác thực các giá trị và xây dựng kết quả có hợp đồng rõ ràng, không phải phát hiện một “nhãn `List<String>`” trên đối tượng gốc. Nếu chỉ kiểm tra rồi tiếp tục giữ danh sách gốc có thể bị thay đổi qua tham chiếu khác, kết luận về các phần tử đã quan sát không bảo đảm dữ liệu sẽ luôn giữ nguyên sau đó.

Mẫu này giả định nguồn không bị sửa đồng thời trong lúc duyệt. Các ràng buộc về đồng thời, `null`, khả năng sửa và sao chép phải được API quy định riêng.

## 9. Chương trình hoàn chỉnh

Lưu vào `ReifiableDemo.java`, dùng Java 17 trở lên:

```java
import java.util.ArrayList;
import java.util.List;

public class ReifiableDemo {
    static List<String> declaredNames() {
        return List.of("declared");
    }

    static List<String> copyStrings(Object candidate) {
        if (!(candidate instanceof List<?> values)) {
            throw new IllegalArgumentException("Expected a list");
        }
        List<String> result = new ArrayList<>();
        for (Object value : values) {
            if (!(value instanceof String text)) {
                throw new IllegalArgumentException("Expected non-null strings");
            }
            result.add(text);
        }
        return List.copyOf(result);
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        ArrayList<String> strings = new ArrayList<>(List.of("Java"));
        ArrayList<Integer> integers = new ArrayList<>(List.of(1));
        System.out.println("same class = " + strings.getClass().equals(integers.getClass()));

        Object candidate = strings;
        if (candidate instanceof List<?> values) {
            System.out.println("list size = " + values.size());
        }

        List<String> known = strings;
        if (known instanceof ArrayList<String> array) {
            System.out.println("refined size = " + array.size());
        }

        List<?>[] buckets = new List<?>[2];
        buckets[0] = List.of("A");
        buckets[1] = List.of(1);
        System.out.println("buckets = " + buckets[0] + " | " + buckets[1]);

        Object[] alias = buckets;
        try {
            alias[0] = "not a list";
        } catch (ArrayStoreException ex) {
            System.out.println(ex.getClass().getSimpleName());
        }

        Class<?> listToken = List.class;
        System.out.println("is list = " + listToken.isInstance(candidate));
        var method = ReifiableDemo.class.getDeclaredMethod("declaredNames");
        System.out.println("return class = " + method.getReturnType().getTypeName());
        System.out.println("generic declaration = " + method.getGenericReturnType().getTypeName());
        System.out.println("validated = " + copyStrings(candidate));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -Xlint:unchecked -encoding UTF-8 ReifiableDemo.java
java ReifiableDemo
```

Kết quả chuẩn:

```text
same class = true
list size = 1
refined size = 1
buckets = [A] | [1]
ArrayStoreException
is list = true
return class = java.util.List
generic declaration = java.util.List<java.lang.String>
validated = [Java]
```

Những điểm cần đối chiếu với mã:

- Hai `ArrayList` có đối số kiểu khác nhau vẫn có cùng lớp thực thi.
- Từ `Object`, kiểm tra `List<?>` cho phép dùng danh sách mà không khẳng định kiểu phần tử cụ thể.
- Kiểm tra `ArrayList<String>` hợp lệ vì toán hạng đã có kiểu tĩnh `List<String>`.
- `List<?>[]` chấp nhận các danh sách có kiểu phần tử khác nhau nhưng từ chối lưu một `String` vào ô mảng qua tham chiếu `Object[]`.
- Reflection đọc được khai báo `List<String>` của phương thức; điều đó khác với việc kiểm tra nội dung đối tượng.
- Hàm `copyStrings` tạo kết quả có kiểu `List<String>` bằng việc kiểm tra từng phần tử, không dùng cast unchecked.

## 10. Những nhầm lẫn cần tránh

**“Mọi kiểu generic đều không reifiable.”** Không. `List<?>` và `Map<?, ?>` là các ví dụ reifiable quan trọng.

**“`List<Object>` cũng giống `List<?>`.”** Không. Kiểu thứ nhất có một đối số kiểu cụ thể; kiểu thứ hai không yêu cầu biết kiểu phần tử cụ thể.

**“Reflection đọc được `List<String>` nên JVM kiểm tra được mọi danh sách chuỗi.”** Không. Metadata khai báo và nội dung từng đối tượng là hai nguồn thông tin khác nhau.

**“Không reifiable thì không thể dùng sau `instanceof` trong mọi trường hợp.”** Không. Quy tắc hiện đại xét cả kiểu tĩnh của toán hạng và tính kiểm tra được của phép chuyển đổi; ví dụ thu hẹp `List<String>` thành `ArrayList<String>` ở trên là hợp lệ.

**“Đã kiểm tra một phần tử là `String` thì cả danh sách là `List<String>`.”** Không. Phần tử khác có thể có kiểu khác, danh sách có thể chứa `null`, và dữ liệu có thể thay đổi qua tham chiếu khác.

**“`new ArrayList<String>()` bị cấm vì kiểu không reifiable.”** Không. Tạo một đối tượng generic là hợp lệ. Đừng nhầm với hạn chế tạo mảng có kiểu thành phần không reifiable.

## 11. Tự kiểm tra

**Câu 1.** `List<?>[]` có reifiable không, và có thể tạo bằng `new List<?>[3]` không?

Có trong cả hai trường hợp. Kiểu thành phần `List<?>` reifiable, và nó không hứa một kiểu phần tử cụ thể cho các danh sách con.

**Câu 2.** Vì sao `List<String>` và `List<Object>` đều không reifiable dù `String` và `Object` là những lớp rõ ràng?

Vì yêu cầu cần biểu đạt là đối số kiểu của danh sách, không phải chỉ nhận diện từng lớp `String` hoặc `Object` đứng riêng. Đối số kiểu cụ thể đó bị xóa khỏi danh tính lớp của đối tượng danh sách thông thường.

**Câu 3.** `List.class.isInstance(value)` có đủ để trả về `List<String>` bằng một cast không cảnh báo không?

Không. Nó chỉ xác nhận `List`. Nếu nguồn chưa có quan hệ kiểu tĩnh phù hợp, cần một quy trình xác thực giá trị hoặc một hợp đồng kiểu khác.

**Câu 4.** Thấy `instanceof ArrayList<String>` có thể kết luận ngay mã sai không?

Không. Phải đọc kiểu tĩnh của toán hạng bên trái. Trường hợp bắt đầu từ `List<String>` có thể hợp lệ; bắt đầu từ `Object` không có cùng bằng chứng kiểu.
