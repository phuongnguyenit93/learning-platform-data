# Phân biệt ghi đè với nạp chồng

## Cùng tên phương thức chưa đủ để kết luận

Trong một hệ phân cấp lớp, phương thức cùng tên có thể phục vụ hai ý định:

- **Ghi đè (overriding):** lớp con cung cấp cách thực hiện cho một phương thức instance trong hợp đồng của kiểu cha.
- **Nạp chồng (overloading):** cung cấp các phương thức cùng tên nhưng có danh sách tham số khác nhau, để xử lý các dạng đầu vào khác nhau.

Kiểu trả về đồng biến gắn với ghi đè: lớp con có thể trả về một kiểu tham chiếu hẹp hơn nhưng vẫn phù hợp với hợp đồng cha. Nó không biến việc chỉ đổi kiểu trả về thành một overload hợp lệ.

Bài dùng Java 17+, phương thức instance thông thường và các kiểu không generic để tách rõ việc chọn overload với việc thực thi bản ghi đè.

## So sánh hai cơ chế

| Nội dung | Ghi đè | Nạp chồng |
| --- | --- | --- |
| Mục tiêu | Thay cách thực hiện một hợp đồng ở kiểu con | Thêm các lựa chọn đầu vào cùng tên |
| Quan hệ kiểu | Xảy ra trong quan hệ kiểu con và kiểu cha | Có thể ngay trong một lớp hoặc qua tập phương thức được kế thừa |
| Tham số trong các ví dụ không generic | Giữ cùng tên và kiểu tham số tương ứng | Khác số lượng, kiểu hoặc thứ tự kiểu tham số |
| Kiểu trả về | Phải phù hợp quy tắc ghi đè, có thể đồng biến với kiểu tham chiếu | Chỉ đổi kiểu trả về không đủ tạo overload |
| Thời điểm quyết định chính | Bản thực hiện instance được chọn theo đối tượng lúc chạy | Chữ ký được chọn lúc biên dịch lời gọi |

Trong Java, chữ ký phương thức không dùng kiểu trả về làm thành phần để phân biệt các overload. Với generic, còn có các quy tắc chữ ký và subsignature chi tiết hơn; bảng tập trung vào các ví dụ đơn giản trong bài. Xem [chữ ký phương thức trong JLS](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.4.2).

## Ví dụ hoàn chỉnh: cùng một đối tượng, hai kiểu tham chiếu

Lưu tệp `OverrideOverloadDemo.java`:

```java
public final class OverrideOverloadDemo {
    private OverrideOverloadDemo() {
    }

    static class Renderer {
        public CharSequence render(Object value) {
            return "base:" + String.valueOf(value);
        }
    }

    static final class TextRenderer extends Renderer {
        @Override
        public String render(Object value) {
            return "object:" + String.valueOf(value);
        }

        public String render(String value) {
            return "string:" + String.valueOf(value);
        }
    }

    public static void main(String[] args) {
        TextRenderer specific = new TextRenderer();
        Renderer general = specific;
        String text = "An";
        Object asObject = text;

        System.out.println("sameReceiver: " + (specific == general));
        System.out.println("general.text: " + general.render(text));
        System.out.println("specific.text: " + specific.render(text));
        System.out.println("specific.object: " + specific.render(asObject));
        System.out.println("specific.cast: " + specific.render((String) asObject));

        String narrowResult = specific.render(Integer.valueOf(7));
        CharSequence broadResult = general.render(Integer.valueOf(7));
        System.out.println("narrowResult: " + narrowResult);
        System.out.println("broadResult: " + broadResult);

        System.out.println("specific.null: " + specific.render(null));
        System.out.println("specific.objectNull: " + specific.render((Object) null));
        System.out.println("general.null: " + general.render(null));
    }
}
```

Biên dịch và chạy tại thư mục chứa tệp bằng JDK 17 trở lên:

```shell
javac --release 17 -encoding UTF-8 -Xlint:all -Werror OverrideOverloadDemo.java
java OverrideOverloadDemo
```

Stdout chính xác:

```text
sameReceiver: true
general.text: object:An
specific.text: string:An
specific.object: object:An
specific.cast: string:An
narrowResult: object:7
broadResult: object:7
specific.null: string:null
specific.objectNull: object:null
general.null: object:null
```

`specific` và `general` cùng tham chiếu một đối tượng `TextRenderer`. `text` và `asObject` cũng cùng tham chiếu chuỗi `"An"`, nhưng kiểu khai báo của hai biến khác nhau.

## Nhận diện đúng hai khai báo trong lớp con

### `render(Object)` là bản ghi đè với kiểu trả về đồng biến

Lớp cha khai báo `CharSequence render(Object)`. Lớp con khai báo `String render(Object)` với `@Override`.

Tên và kiểu tham số được giữ nguyên; kết quả `String` hẹp hơn `CharSequence` vì `String` triển khai `CharSequence`. Đây là thay đổi kiểu trả về hợp lệ trong ghi đè, không phải một overload chỉ khác kiểu trả về.

Người gọi qua kiểu cha vẫn có thể nhận kết quả như một `CharSequence`. Người gọi trực tiếp qua kiểu con thấy hợp đồng hẹp hơn là `String`. Xem [quy tắc kiểu kết quả](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.4.5) và [ghi đè phương thức instance](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.4.8.1).

### `render(String)` là overload

Phương thức này đổi kiểu tham số từ `Object` sang `String`. Nó không ghi đè `render(Object)`; nó tạo thêm lựa chọn nạp chồng cho mã có thể truy cập khai báo đó.

Lớp cha `Renderer` không công bố `render(String)`, nên một biểu thức có kiểu tĩnh `Renderer` không tự nhìn thấy overload chỉ có ở `TextRenderer`.

Thay đổi tham số thành kiểu hẹp hơn không phải “ghi đè đồng biến tham số”. Java không dùng quy tắc kiểu trả về đồng biến để cho phép thu hẹp danh sách tham số trong ghi đè. Xem [nạp chồng trong JLS](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.4.9).

## Phân tích một lời gọi theo hai bước

Đối với các phương thức instance trong ví dụ, có thể lần lượt hỏi:

1. **Lúc biên dịch:** từ kiểu tĩnh của biểu thức nhận lời gọi và kiểu của đối số, chữ ký overload nào được chọn?
2. **Lúc chạy:** với chữ ký instance đã chọn, đối tượng thực tế sử dụng bản ghi đè nào?

Không đảo hai bước bằng cách nhìn lớp thực của mọi đối số rồi chọn lại overload khi chạy. Quy tắc chọn chữ ký diễn ra khi biên dịch. Xem [quá trình xác định phương thức được gọi](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.12.2).

| Lời gọi | Chữ ký được chọn khi biên dịch | Phần thân chạy |
| --- | --- | --- |
| `general.render(text)` | `Renderer.render(Object)` | Bản ghi đè `TextRenderer.render(Object)` |
| `specific.render(text)` | `TextRenderer.render(String)` | `TextRenderer.render(String)` |
| `specific.render(asObject)` | `TextRenderer.render(Object)` | `TextRenderer.render(Object)` |
| `specific.render((String) asObject)` | `TextRenderer.render(String)` | `TextRenderer.render(String)` |

### Vì sao `general.render(text)` không vào overload `String`?

`general` có kiểu tĩnh `Renderer`. Trong kiểu này, phương thức phù hợp đang thấy là `render(Object)`, và một `String` có thể truyền vào tham số `Object`.

Khi chạy, đối tượng thật là `TextRenderer`, nên bản ghi đè của **`render(Object)`** được dùng. Kết quả là `object:An`, không phải `base:An` và cũng không phải `string:An`.

### Vì sao hai biến cùng giữ một chuỗi lại chọn khác nhau?

`text` có kiểu tĩnh `String`, nên khi gọi qua `specific`, overload nhận `String` phù hợp và cụ thể hơn overload nhận `Object`.

`asObject` có kiểu tĩnh `Object`. Dù giá trị bên trong là một chuỗi, trình biên dịch không tự coi mọi biến `Object` là `String`; lời gọi chọn phương thức nhận `Object`.

Phép ép `(String) asObject` làm biểu thức đối số có kiểu `String`, nên ảnh hưởng tới chọn overload. Nó đồng thời là một kiểm tra lúc chạy: nếu `asObject` không thực sự phù hợp `String`, phép ép có thể ném `ClassCastException` trước khi lời gọi xảy ra.

## Kiểu trả về hẹp hơn không đổi kiểu tĩnh của lời gọi qua cha

`specific.render(Integer.valueOf(7))` chọn phương thức nhận `Object`. Qua kiểu `TextRenderer`, phương thức đó trả `String`, nên có thể gán vào `String narrowResult`.

`general.render(Integer.valueOf(7))` vẫn chạy cùng bản thực hiện lúc chạy, nhưng kiểu tĩnh của lời gọi là `CharSequence` theo hợp đồng `Renderer`. Vì vậy bài nhận nó vào `CharSequence broadResult`.

Dòng dưới đây **không biên dịch** nếu đặt trong `main` với các biến của ví dụ:

```java
// String wrong = general.render(text);
```

Kiểu thật của kết quả khi chạy là `String` không làm trình biên dịch tự hạ kiểu của biểu thức có hợp đồng trả về `CharSequence`. Cần chọn API và kiểu tham chiếu theo nhu cầu; không thêm ép kiểu chỉ để bỏ qua một hợp đồng chưa được chứng minh.

## `null` cho thấy sự khác biệt về overload

`specific.render(null)` có thể phù hợp cả tham số `Object` và `String`; giữa hai lựa chọn này, `String` cụ thể hơn nên được chọn. Vì vậy kết quả là `string:null`.

`specific.render((Object) null)` đã chỉ rõ kiểu đối số là `Object`, nên chọn bản nhận `Object`. `general.render(null)` cũng chỉ thấy hợp đồng `render(Object)` qua kiểu cha, rồi thực thi bản ghi đè lúc chạy.

Không suy ra rằng mọi lời gọi có `null` đều có một overload cụ thể nhất. Nếu thêm hai overload nhận những kiểu tham chiếu không có quan hệ kiểu con với nhau, lời gọi `null` có thể mơ hồ và bị từ chối khi biên dịch.

## Dùng `@Override` để phát hiện nhầm ý định

Nếu tác giả muốn ghi đè nhưng vô tình viết `render(String)`, đặt `@Override` lên phương thức đó sẽ giúp trình biên dịch báo rằng nó không ghi đè phương thức tương ứng trong kiểu cha của ví dụ.

`@Override` không tạo ra quan hệ ghi đè. Quan hệ do khai báo và quy tắc ngôn ngữ xác định; annotation thể hiện ý định để trình biên dịch kiểm tra. Xem [`Override`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Override.html).

Ví dụ không biên dịch có chủ ý, dùng trong một tệp thử riêng:

```java
class ParentExample {
    public Object transform(Object value) {
        return value;
    }
}

class ChildExample extends ParentExample {
    @Override
    public String transform(String value) {
        return value;
    }
}
```

Nếu mục tiêu là ghi đè với kết quả hẹp hơn, phải giữ tham số `Object` và trả `String` bằng một cách cài đặt phù hợp. Nếu mục tiêu là thêm overload cho chuỗi, bỏ ý định ghi đè và giữ cả hai hợp đồng rõ ràng.

## Chỉ đổi kiểu trả về không tạo được overload

Không thể khai báo hai phương thức trong cùng lớp chỉ khác kiểu trả về như `Object load()` và `String load()`. Chúng có cùng chữ ký ở mức nguồn, nên trình biên dịch từ chối trước khi có vấn đề chọn theo biến nhận kết quả.

Đừng dựa vào suy nghĩ “gán vào `String` thì gọi phiên bản trả `String`”. Với hai khai báo chỉ khác kiểu kết quả như trên, tập phương thức đã không hợp lệ.

Quy tắc này khác với trường hợp hợp lệ ở ví dụ chính: `Renderer.render(Object)` nằm trong kiểu cha và `TextRenderer.render(Object)` là bản ghi đè có kiểu trả về tương thích. Đây là một hợp đồng được chuyên biệt hóa trong quan hệ kiểu con.

## Những ràng buộc cần giữ khi phân loại

- Phương thức `static` không tham gia ghi đè instance như ví dụ; cùng chữ ký ở kiểu con có thể là che khuất (hiding), không phải phân phối động theo đối tượng.
- Phương thức `private` của cha không được lớp con ghi đè như một phương thức được kế thừa; phương thức `final` không thể bị ghi đè.
- Bản ghi đè còn phải thỏa các điều kiện về khả năng truy cập và ngoại lệ được kiểm tra; chỉ cùng tên và tham số chưa đủ để bỏ qua các điều kiện đó.
- Kiểu trả về nguyên thủy không được thu hẹp theo cách `long` thành `int` chỉ vì một giá trị cụ thể nhỏ hơn; đồng biến kiểu tham chiếu là một quy tắc khác.

Bài tập trung vào hai bước chọn lời gọi trong phương thức instance. Khi gặp generic, boxing hoặc varargs phức tạp, hãy kiểm tra quy tắc chi tiết thay vì mở rộng máy móc một ví dụ overload đơn giản.

## Thực hành kiểm chứng

1. Đổi `Renderer general = specific` thành một biến mới `TextRenderer sameType = specific`, rồi gọi `sameType.render(text)`. Nó chọn overload `String` dù đối tượng vẫn là đối tượng cũ.
2. Bỏ overload `render(String)` khỏi `TextRenderer`. Các lời gọi chuỗi qua lớp con giờ dùng `render(Object)`; chúng vẫn gọi bản ghi đè, không quay về phần thân `base`.
3. Giữ overload nhưng đổi đối số từ `text` sang `asObject`. Giải thích bằng kiểu tĩnh trước khi chạy.
4. Thêm `@Override` vào `render(String)` của ví dụ chính để kiểm tra trình biên dịch từ chối ý định ghi đè sai.
5. Thử gán kết quả `general.render(text)` vào `String` trong một tệp thử; trình biên dịch phải báo không tương thích kiểu dù bản thực hiện runtime trả một chuỗi.

Người học cần xác định được chữ ký được chọn trước khi xét đối tượng runtime, và chỉ ra kiểu trả về đồng biến làm hẹp kết quả ở bản ghi đè mà không tạo một overload mới.