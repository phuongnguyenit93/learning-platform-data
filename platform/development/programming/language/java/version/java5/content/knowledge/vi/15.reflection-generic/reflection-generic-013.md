# Giới hạn suy ra đối số kiểu của một đối tượng bất kỳ

## Câu hỏi cần đặt chính xác

Khi nhận một giá trị `Object`, ta có thể muốn hỏi “đối tượng này là `Box<String>` hay `Box<Integer>`?” hoặc “danh sách này có đối số kiểu là gì?”. Trong Java, không có một hàm tổng quát luôn trả lời chính xác câu hỏi ấy cho mọi đối tượng chỉ dựa vào `getClass()`.

Lý do nằm ở xóa kiểu (type erasure): nhiều cách sử dụng một lớp generic chia sẻ cùng lớp lúc chạy. Tuy vậy, không được kết luận rằng **mọi thông tin generic đều biến mất**. Chữ ký của trường, phương thức, lớp cha và interface có thể giữ thông tin của khai báo. Xem [xóa kiểu trong JLS](https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.6).

Bài dùng Java 17+ để phân biệt ba việc: đọc lớp thực, đọc metadata generic của một khai báo và quan sát kiểu của dữ liệu đang chứa bên trong.

## Những nguồn thông tin có thể có

| Nguồn đang có | Biết được gì? | Không tự biết được gì? |
| --- | --- | --- |
| Chỉ một instance của `Box<T>` thông thường | Lớp thực là `Box`; khai báo lớp có biến `T` | Đối số `T` được viết ở mọi nơi gọi `new Box<...>()` |
| `Field` khai báo `List<String>` | Chữ ký generic của trường là `List<String>` | Mọi phần tử hiện tại hoặc tương lai chắc chắn là chuỗi |
| Lớp con `StringBox extends Box<String>` | Chữ ký lớp cha có `Box<String>` | Đối số của một đối tượng khác chỉ vì nó cũng có dữ liệu chuỗi |
| Một phần tử hiện đang là `Integer` | Lớp thực của phần tử đó | Danh sách chứa nó được khai báo `List<Integer>`, `List<Number>` hay `List<Object>` |

Cần trả lời từ đúng nguồn và ghi rõ giới hạn. Không đổi “chưa biết” thành một lớp được đoán từ dữ liệu tình cờ.

## Ví dụ hoàn chỉnh

Lưu tệp `GenericInferenceLimitsDemo.java`:

```java
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.Type;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

public final class GenericInferenceLimitsDemo {
    private GenericInferenceLimitsDemo() {
    }

    static class Box<T> {
        private final T value;

        Box(T value) {
            this.value = value;
        }

        T value() {
            return value;
        }
    }

    static final class StringBox extends Box<String> {
        StringBox(String value) {
            super(value);
        }
    }

    static class Mid<U> extends Box<List<U>> {
        Mid(List<U> value) {
            super(value);
        }
    }

    static final class StringLists extends Mid<String> {
        StringLists() {
            super(List.of("An"));
        }
    }

    static class Holder {
        List<String> names;
    }

    private static String describe(Type type) {
        if (type instanceof ParameterizedType parameterized
                && parameterized.getRawType() instanceof Class<?> raw) {
            String arguments = Arrays.stream(parameterized.getActualTypeArguments())
                    .map(Type::getTypeName).collect(Collectors.joining(", "));
            return raw.getSimpleName() + "<" + arguments + ">";
        }
        return type.getTypeName();
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        Box<String> text = new Box<>("An");
        Box<Integer> number = new Box<>(7);
        System.out.println("sameBoxClass: " + (text.getClass() == number.getClass()));
        System.out.println("runtimeClass: " + text.getClass().getSimpleName());
        System.out.println("declaredVariable: "
                + text.getClass().getTypeParameters()[0].getName());
        System.out.println("firstValueClass: " + text.value().getClass().getSimpleName());
        System.out.println("secondValueClass: " + number.value().getClass().getSimpleName());

        Box<String> missingText = new Box<>(null);
        Box<Number> missingNumber = new Box<>(null);
        System.out.println("sameNullBoxClass: "
                + (missingText.getClass() == missingNumber.getClass()));

        StringBox named = new StringBox("Binh");
        Box<String> anonymous = new Box<String>("Chi") {
        };
        System.out.println("namedSuperclass: "
                + describe(named.getClass().getGenericSuperclass()));
        System.out.println("anonymousSuperclass: "
                + describe(anonymous.getClass().getGenericSuperclass()));

        System.out.println("firstHop: "
                + describe(StringLists.class.getGenericSuperclass()));
        System.out.println("secondHop: "
                + describe(Mid.class.getGenericSuperclass()));

        System.out.println("fieldMetadata: "
                + Holder.class.getDeclaredField("names").getGenericType().getTypeName());

        List<Number> mixed = new ArrayList<>();
        mixed.add(Integer.valueOf(1));
        System.out.println("observedFirst: " + mixed.get(0).getClass().getSimpleName());
        mixed.add(Double.valueOf(2.5));
        System.out.println("observedSecond: " + mixed.get(1).getClass().getSimpleName());

        List<String> emptyText = new ArrayList<>();
        List<Integer> emptyNumbers = new ArrayList<>();
        System.out.println("sameEmptyListClass: "
                + (emptyText.getClass() == emptyNumbers.getClass()));
    }
}
```

Biên dịch và chạy tại thư mục chứa tệp bằng JDK 17 trở lên:

```shell
javac --release 17 -encoding UTF-8 -Xlint:all -Werror GenericInferenceLimitsDemo.java
java GenericInferenceLimitsDemo
```

Stdout chính xác:

```text
sameBoxClass: true
runtimeClass: Box
declaredVariable: T
firstValueClass: String
secondValueClass: Integer
sameNullBoxClass: true
namedSuperclass: Box<java.lang.String>
anonymousSuperclass: Box<java.lang.String>
firstHop: Mid<java.lang.String>
secondHop: Box<java.util.List<U>>
fieldMetadata: java.util.List<java.lang.String>
observedFirst: Integer
observedSecond: Double
sameEmptyListClass: true
```

Hàm `describe` chỉ dùng để trình bày ngắn tên kiểu gốc của lớp cha trong ví dụ. Nó không phải thuật toán suy ra hoặc phân giải biến kiểu; dữ liệu vẫn được đọc từ `Type` và `ParameterizedType`.

## Instance thông thường không tự mang một `Class` cho mỗi đối số kiểu

`text` là `Box<String>`, còn `number` là `Box<Integer>` ở mức kiểm tra kiểu của mã nguồn. Nhưng `text.getClass()` và `number.getClass()` cùng mô tả `Box`, nên dòng `sameBoxClass` là `true`.

`getTypeParameters()` trên lớp đó trả biến `T` của khai báo `Box<T>`. Nó không phải danh sách đối số kiểu đã được chọn khi tạo từng đối tượng. Tên `T` trong đầu ra là biến khai báo, không phải kết quả suy luận `String` hoặc `Integer`.

Đọc `value().getClass()` cho `String` hoặc `Integer` chỉ vì giá trị hiện tại có các lớp đó. Hai `Box` với giá trị `null` cũng có thể được dùng dưới các đối số kiểu khác nhau, trong khi không có đối tượng bên trong để khảo sát.

Trong một API chỉ nhận `Object`, chữ viết của biến tại nơi gọi không tự đi theo đối tượng như một bản chụp kiểu generic. Muốn dùng thông tin ấy, API phải nhận thêm một mô tả kiểu hoặc một ngữ cảnh khai báo thích hợp.

## Khi nào lớp con giữ được đối số cụ thể?

`StringBox` là một lớp riêng có khai báo `extends Box<String>`. Phần `String` là thông tin trong chữ ký lớp cha của **lớp con**, nên `getGenericSuperclass()` có thể đọc lại nó.

Lớp vô danh trong `new Box<String>("Chi") {}` cũng có một khai báo lớp cha `Box<String>` trong metadata của lớp được tạo. Dấu `{}` ở đây tạo lớp con vô danh; nó khác `new Box<String>("Chi")` thông thường.

Xem hợp đồng của [`Class.getGenericSuperclass()`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Class.html#getGenericSuperclass()).

Đây là đọc thông tin được giữ lại bởi một khai báo cụ thể, không phải vượt qua xóa kiểu để khôi phục mọi đối số từ instance bất kỳ. Nếu chữ ký lớp con chỉ còn biến kiểu chưa được gán cụ thể, kết quả cũng có thể còn biến kiểu.

Ví dụ, một lớp con `GenericBox<X> extends Box<X>` có thể công bố `Box<X>`; tạo `new GenericBox<String>(...)` thông thường không khiến `getGenericSuperclass()` của lớp đó tự trả `Box<String>`.

Các cơ chế giữ kiểu bằng lớp con cũng cần được dùng đúng: nếu tạo lớp con vô danh bên trong phương thức generic và viết `new SomeToken<T>() {}`, chữ ký có thể giữ **biến `T` của phương thức**, không phải đối số cụ thể của mọi lần gọi.

## Chuỗi lớp cha có thể cần phân giải nhiều bước

`StringLists` công bố lớp cha `Mid<String>`. `Mid<U>` lại công bố lớp cha `Box<List<U>>`. Hai dòng `firstHop` và `secondHop` thể hiện hai mảnh thông tin khác nhau.

Muốn diễn giải kiểu tham số của `Box` trong ngữ cảnh `StringLists`, bộ phân giải cần:

1. Từ `StringLists extends Mid<String>`, lập ánh xạ biến `U` của `Mid` sang `String`.
2. Đọc `Mid extends Box<List<U>>`.
3. Thay `U` theo ánh xạ để có `Box<List<String>>` trong ngữ cảnh đang xét.

Chỉ lấy `getActualTypeArguments()[0]` từ lớp cha trực tiếp của `StringLists` rồi kết luận đó là đối số của mọi lớp generic trong chuỗi là sai. Đối số trực tiếp đang thuộc `Mid`; với `Box`, cấu trúc cần suy ra là một `List<String>`.

Các đối số của `ParameterizedType` là `Type`, không bắt buộc là `Class`. Chúng có thể lồng nhau hoặc chứa biến kiểu. Xem [`ParameterizedType`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/ParameterizedType.html).

Một bộ phân giải đầy đủ còn phải xét các nhánh interface, kiểu chủ của lớp thành viên, wildcard, mảng generic và các biến cùng tên ở nơi khai báo khác nhau. Bài chỉ minh họa giới hạn và các nguồn metadata; không giả định một phép ép kiểu ngắn là đủ xử lý mọi cấu trúc.

## Vì sao quan sát phần tử không khôi phục được khai báo?

`mixed` được khai báo `List<Number>`. Phần tử đầu là `Integer`; sau đó chương trình thêm `Double` hoàn toàn hợp lệ, không cần raw type hoặc phép ép kiểu không được kiểm tra.

Nếu một thuật toán chỉ xem phần tử đầu rồi công bố “đây là `List<Integer>`”, nó đã đưa ra kết luận sai ngay trên mã an toàn kiểu. Cùng một tập dữ liệu chỉ gồm số nguyên cũng có thể đang nằm trong `List<Number>` hoặc `List<Object>`.

Ngay cả kiểm tra mọi phần tử hiện có cũng chỉ trả lời một câu hỏi về **dữ liệu hiện tại**. Nó không xác định duy nhất đối số generic đã được viết trong nguồn và không tự hạn chế mọi thay đổi sau đó.

Danh sách rỗng và phần tử `null` làm giới hạn này rõ hơn: không có đủ bằng chứng để chọn một kiểu phần tử cụ thể. Chọn `Object` có thể là một chính sách mặc định cho ứng dụng, nhưng phải được mô tả là chính sách, không phải metadata đã khôi phục.

Với cấu trúc lồng như `List<List<String>>`, chỉ biết phần tử ngoài là một `ArrayList` càng không xác định được các đối số kiểu ở cấp trong.

## Metadata của trường cũng là một ngữ cảnh, không phải dữ liệu tự mang theo

`Holder.names` khai báo `List<String>` nên `Field.getGenericType()` đọc được chữ ký đó. Dòng `fieldMetadata` chứng minh thông tin generic có thể tồn tại trong metadata dù các instance generic thông thường chia sẻ lớp.

Nhưng một đối tượng danh sách được truyền sang nơi khác không tự mang một con trỏ tới “trường gốc duy nhất” để truy ngược khai báo. Cùng một đối tượng còn có thể được giữ bởi nhiều biến hoặc được quan sát qua những kiểu tham chiếu khác nhau.

Đối với một trường kiểu `T` trong lớp generic, `Field` vẫn mô tả biến `T`. Muốn thay bằng kiểu cụ thể phải cung cấp ngữ cảnh sử dụng; việc đang có một giá trị trong trường không tự giải quyết phép phân giải này.

## Thiết kế API khi cần biết kiểu

Tùy nhu cầu, hãy chọn thông tin bổ sung rõ ràng:

| Nhu cầu | Hướng thiết kế |
| --- | --- |
| Kiểm tra một giá trị có phù hợp lớp cụ thể như `String` không | Nhận `Class<T>` và dùng `cast` hoặc `isInstance` |
| Mô tả kiểu lồng như `List<String>` | Nhận `Type` hoặc một cơ chế giữ cấu trúc kiểu đã được thiết kế đúng |
| Đọc kiểu từ mô hình đối tượng có khai báo trường/phương thức | Nhận cả metadata khai báo và ngữ cảnh cần phân giải |
| Kiểm tra nội dung của một tập hợp | Nhận quy tắc kiểm tra dữ liệu rõ ràng, không gọi nó là khôi phục generic |

`Class<List>` hoặc `List.class` chỉ đại diện lớp/interface ở mức runtime; không biểu diễn riêng `List<String>`. Với một `Class` như vậy, phép `cast` không tự kiểm tra từng phần tử của danh sách.

Java cũng không cho viết `List<String>.class`; với một biến `Object value`, không thể dùng `value instanceof List<String>` để nhận diện generic đầy đủ. Có thể kiểm tra `value instanceof List<?>` để biết nó là `List`, nhưng wildcard này không cung cấp một đối số cụ thể để dùng như `String.class`.

Nếu API nhận một `Type`, thông tin đó là hợp đồng được truyền vào từ nguồn đã chọn. Nó không tự chứng minh dữ liệu thực phù hợp cấu trúc đã mô tả; phần xác minh dữ liệu vẫn có thể cần thiết.

## Những kết luận nên tránh

- “Gọi `getTypeParameters()` là biết các kiểu đã truyền khi tạo object”: API đó đọc biến kiểu do lớp khai báo.
- “Phần tử đầu là `String` nên đó là `List<String>`”: dữ liệu hiện tại không xác định duy nhất khai báo.
- “Dùng lớp vô danh là lấy được generic của mọi đối tượng”: chỉ đọc được thông tin mà chữ ký lớp con thực sự ghi lại.
- “Có một `ParameterizedType` nên mọi đối số đều là `Class`”: đối số có thể là kiểu lồng, wildcard hoặc biến chưa phân giải.
- “Không suy ra được thì trả `Object.class` và coi như thành công”: cần phân biệt kiểu được xác định là `Object` với trường hợp chưa biết.

Metadata có thể bị công cụ xử lý bytecode loại bỏ hoặc tham chiếu kiểu không có mặt trong môi trường chạy. Một API phản chiếu nên báo rõ thiếu ngữ cảnh, kiểu chưa phân giải hoặc lỗi metadata; không bịa một kết quả cụ thể.

## Thực hành kiểm chứng

1. Đổi `Box<Integer> number` thành `Box<Number> number` nhưng giữ giá trị `7`. Lớp thực của hộp và giá trị vẫn giống trước; khai báo khác không tự làm xuất hiện một `Class` runtime mới.
2. Đổi phần tử đầu của `mixed` sang `Double`, rồi thêm `Integer`. Khai báo vẫn là `List<Number>`; thứ tự quan sát không xác định đối số generic.
3. Bỏ `{}` ở lần tạo `anonymous`, biến nó thành `new Box<String>("Chi")`. Khi đó lớp thực là `Box`, lớp cha generic của nó là `Object`, không còn chữ ký lớp con `Box<String>` ở vị trí đang đọc.
4. Đổi `StringLists extends Mid<String>` thành `StringLists extends Mid<Integer>` và cập nhật dữ liệu constructor. `firstHop` đổi theo, còn khai báo của `Mid` vẫn giữ `Box<List<U>>`.
5. Thử một danh sách rỗng và một danh sách chỉ có `null`; nêu rõ nguồn thông tin nào còn có thể dùng trước khi đưa ra kết luận về kiểu.

Sau bài học, cần nói được một kết luận lấy từ lớp runtime, chữ ký khai báo hay dữ liệu quan sát, và khi nào cần thêm ngữ cảnh thay vì cố suy ra một đối số kiểu duy nhất từ đối tượng.