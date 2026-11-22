# Kiểu tĩnh và kiểu thực tế tại nơi gọi phương thức

## Khái niệm: cần theo dõi cả biến, biểu thức và đối tượng

Khi một lời gọi Java dùng đa hình và kiểu trả về đồng biến, có thể đồng thời tồn tại những kiểu khác nhau ở các vị trí khác nhau.

Ví dụ:

```java
Renderer renderer = new HtmlRenderer();
Document result = renderer.render();
```

Đây là mảnh minh họa; các kiểu và chương trình đầy đủ nằm ở phần sau.

Cần tách hai khái niệm:

- **Kiểu tĩnh:** kiểu của biến hoặc biểu thức mà trình biên dịch sử dụng để kiểm tra mã.
- **Kiểu thực tế lúc chạy:** lớp của đối tượng mà một tham chiếu khác `null` đang trỏ tới.

Biến `renderer` có kiểu tĩnh `Renderer`, nhưng đối tượng được tạo là `HtmlRenderer`. Nếu phương thức ghi đè trả một đối tượng `HtmlDocument`, kết quả thực tế là `HtmlDocument`, dù biểu thức `renderer.render()` có thể vẫn có kiểu tĩnh `Document`.

Đây là nền tảng để hiểu vì sao cùng một đối tượng thực tế có thể được sử dụng thông qua các hợp đồng kiểu khác nhau.

Bài dùng ví dụ phương thức không generic để quan sát rõ sự khác biệt, trên JDK 17 trở lên.

## Vì sao kiểu tĩnh không tự đổi theo đối tượng thực tế?

Một biến kiểu cha có thể tham chiếu tới nhiều kiểu con hợp lệ. Mã viết dựa trên kiểu cha cần giữ được tính hợp lệ mà không phụ thuộc vào việc hôm nay biến đang trỏ tới lớp con nào.

Nếu `Renderer` chỉ cam kết `Document render()`, thì lời gọi qua `Renderer` được phép dựa trên cam kết đó. Không thể mặc nhiên đòi thêm các thành viên chỉ một lớp con cụ thể cung cấp.

Kiểu tĩnh giúp trình biên dịch trả lời:

- Có phương thức phù hợp với lời gọi không?
- Những đối số nào được chấp nhận?
- Biểu thức lời gọi có kiểu gì?
- Kết quả có thể gán cho biến nào?
- Thành viên nào có thể gọi tiếp trên kết quả?

Kiểu thực tế của đối tượng lại có vai trò ở việc chọn phần thực thi của phương thức instance được ghi đè, sau khi lời gọi đã được xác định hợp lệ.

Đặc tả phân biệt kiểu của biến/biểu thức với lớp của đối tượng tại [JLS §4.12.6](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.12.6).

## Bốn câu hỏi cho một lời gọi có kiểu trả về đồng biến

Với mô hình:

```text
HtmlRenderer la kieu con cua Renderer
HtmlDocument la kieu con cua Document
```

và các chữ ký:

```java
// Các chữ ký minh họa nằm ở hai lớp khác nhau:
Document render();      // Renderer
HtmlDocument render();  // HtmlRenderer ghi đè
```

hãy hỏi lần lượt:

1. Kiểu tĩnh của biểu thức nhận lời gọi là gì?
2. Chữ ký phương thức mà trình biên dịch sử dụng là gì?
3. Đối tượng nhận lời gọi thực tế thuộc lớp nào?
4. Đối tượng kết quả thực tế thuộc lớp nào?

Ví dụ, nếu `general` có kiểu tĩnh `Renderer` nhưng trỏ tới `HtmlRenderer`:

| Vị trí | Kiểu |
| --- | --- |
| Kiểu tĩnh của general | `Renderer` |
| Kiểu thực tế của đối tượng general trỏ tới | `HtmlRenderer` |
| Kiểu tĩnh của general.render() | `Document` |
| Kiểu thực tế của kết quả trong ví dụ | `HtmlDocument` |

Hai cặp kiểu không cần giống nhau. Đặc biệt, kiểu của đối tượng nhận lời gọi và kiểu của đối tượng kết quả là hai câu hỏi riêng.

## Giai đoạn biên dịch và giai đoạn chạy

Với phương thức instance thông thường có quan hệ ghi đè, có thể hình dung:

```text
Khi bien dich
  Kieu tinh cua bieu thuc nhan loi goi
        |
        v
  Tim chu ky va kiem tra doi so
        |
        v
  Xac dinh kieu tinh cua bieu thuc ket qua
        |
        v
Khi chay
  Doi tuong thuc te nhan loi goi
        |
        v
  Chon phan thuc thi ghi de phu hop
        |
        v
  Tra ve gia tri / doi tuong ket qua
```

Không nên rút gọn thành “Java chọn mọi thứ lúc chạy”. Những việc như kiểm tra thành viên và chọn nạp chồng thông thường được giải quyết khi biên dịch.

Cũng không nên rút gọn thành “kiểu biến quyết định phần thân phương thức”. Với phương thức instance được ghi đè, đối tượng thực tế mới quyết định phần thực thi phù hợp.

Quy trình gọi phương thức được mô tả tại [JLS §15.12](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.12).

## Chương trình đầy đủ

Lưu thành `CallSiteTypesDemo.java`:

```java
public class CallSiteTypesDemo {
    static class Document {
        String content() {
            return "plain";
        }
    }

    static class HtmlDocument extends Document {
        @Override
        String content() {
            return "<p>Hello</p>";
        }

        String htmlOnly() {
            return "html-tools";
        }
    }

    static class Renderer {
        Document render() {
            return new Document();
        }
    }

    static class HtmlRenderer extends Renderer {
        @Override
        HtmlDocument render() {
            return new HtmlDocument();
        }
    }

    static String report(Document document) {
        return "Document";
    }

    static String report(HtmlDocument document) {
        return "HtmlDocument";
    }

    public static void main(String[] args) {
        HtmlRenderer specific = new HtmlRenderer();
        Renderer general = specific;

        Document fromGeneral = general.render();
        HtmlDocument fromSpecific = specific.render();

        System.out.println("general.runtime="
                + fromGeneral.getClass().getSimpleName());
        System.out.println("specific.runtime="
                + fromSpecific.getClass().getSimpleName());
        System.out.println("general.content=" + fromGeneral.content());
        System.out.println("specific.extra=" + fromSpecific.htmlOnly());
        System.out.println("report.general=" + report(fromGeneral));
        System.out.println("report.specific=" + report(fromSpecific));

        var inferred = general.render();
        System.out.println("report.var=" + report(inferred));

        if (fromGeneral instanceof HtmlDocument html) {
            System.out.println("report.pattern=" + report(html));
        }
    }
}
```

Biên dịch và chạy:

```shell
javac -encoding UTF-8 CallSiteTypesDemo.java
java CallSiteTypesDemo
```

Kết quả:

```text
general.runtime=HtmlDocument
specific.runtime=HtmlDocument
general.content=<p>Hello</p>
specific.extra=html-tools
report.general=Document
report.specific=HtmlDocument
report.var=Document
report.pattern=HtmlDocument
```

## Phân tích hai lời gọi render

### Gọi qua kiểu cụ thể

```java
HtmlRenderer specific = new HtmlRenderer();
HtmlDocument fromSpecific = specific.render();
```

Kiểu tĩnh `HtmlRenderer` có chữ ký trả `HtmlDocument`. Vì vậy có thể gán kết quả trực tiếp cho biến `HtmlDocument` và gọi `htmlOnly()`.

Không cần ép kiểu vì cam kết cụ thể đã nằm trong chữ ký của phương thức ghi đè mà mã đang nhìn thấy.

### Gọi qua kiểu tổng quát

```java
Renderer general = specific;
Document fromGeneral = general.render();
```

`general` và `specific` cùng trỏ tới một đối tượng renderer, nhưng kiểu tĩnh của hai biến khác nhau.

Lời gọi qua `general` vẫn thực thi `HtmlRenderer.render()`, nên kết quả thực tế là một `HtmlDocument`. Tuy nhiên, kiểu tĩnh của biểu thức `general.render()` là `Document`.

Vì thế, nếu thêm dòng sau vào `main`, nó **cố ý không biên dịch**:

```java
HtmlDocument invalid = general.render();
```

Đối tượng thực tế phù hợp không đủ để tạo một phép thu hẹp kiểu ngầm định ở nơi gán. Khi biên dịch, hợp đồng mà lời gọi qua `Renderer` cung cấp vẫn là `Document`.

Cơ chế trả về đồng biến cho phép khai báo phương thức con cụ thể hơn; nó không tự nâng mọi tham chiếu kiểu cha thành kiểu con. Quy tắc kiểu trả về được mô tả tại [JLS §8.4.8.3](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.4.8.3).

## Tại sao content() vẫn chạy phần thực thi của HtmlDocument?

Biến `fromGeneral` có kiểu tĩnh `Document`, nên lời gọi `fromGeneral.content()` hợp lệ vì `Document` có phương thức đó.

Đối tượng thực tế là `HtmlDocument`, nơi ghi đè `content()`. Vì vậy kết quả là `<p>Hello</p>`.

Đây là một lần điều phối đa hình thứ hai, trên **đối tượng kết quả**:

1. Lời gọi `general.render()` điều phối theo đối tượng renderer thực tế.
2. Lời gọi `fromGeneral.content()` điều phối theo đối tượng document thực tế.

Không được trộn hai bước thành một quy tắc mơ hồ rằng “kiểu cha đã biến thành kiểu con”.

Ngược lại, dòng sau không hợp lệ trong chương trình:

```java
// Cố ý không biên dịch:
fromGeneral.htmlOnly();
```

Kiểu tĩnh `Document` không khai báo `htmlOnly()`. Việc phương thức ấy tồn tại trong đối tượng thực tế không tự làm lời gọi xuất hiện trong hợp đồng của biến kiểu cha.

## Nạp chồng được chọn theo kiểu tĩnh trong ví dụ

Chương trình có hai phương thức tĩnh:

```java
static String report(Document document)
static String report(HtmlDocument document)
```

Hai chữ ký trên minh họa nạp chồng (overloading). Chúng có tên giống nhau nhưng kiểu tham số khác nhau.

Với:

```java
report(fromGeneral);
report(fromSpecific);
```

trình biên dịch chọn:

- `report(Document)` cho `fromGeneral`, vì kiểu tĩnh của đối số là `Document`.
- `report(HtmlDocument)` cho `fromSpecific`, vì kiểu tĩnh của đối số là `HtmlDocument` và chữ ký này cụ thể hơn trong tập ứng viên phù hợp.

Đó là lý do output khác nhau dù cả hai giá trị đang trỏ tới các đối tượng `HtmlDocument`.

Không có bước tự kiểm tra `getClass()` của đối số rồi chọn lại overload khi chương trình chạy. Hai hàm `report` trong ví dụ là static để quan sát riêng việc chọn overload, không trộn với ghi đè của chính hàm `report`.

Nếu hàm được chọn tiếp tục gọi một phương thức instance trên đối số, lần gọi instance đó vẫn có thể dùng đa hình. “Nạp chồng chọn lúc biên dịch” không có nghĩa mọi lời gọi bên trong phần thân cũng mất đa hình.

## var không có nghĩa là kiểu động

Trong chương trình:

```java
var inferred = general.render();
```

trình biên dịch suy ra kiểu của `inferred` từ kiểu của biểu thức khởi tạo. Với lời gọi qua `general` trong ví dụ, kiểu đó là `Document`.

Vì vậy `report(inferred)` chọn `report(Document)` và in `report.var=Document`.

`var` không chờ đến lúc chạy để gọi `getClass()` của đối tượng rồi gán một kiểu mới cho biến. Nó là suy luận kiểu biến cục bộ lúc biên dịch.

So sánh:

```java
var a = general.render();   // Document trong ví dụ
var b = specific.render();  // HtmlDocument trong ví dụ
```

Hai dòng đều dùng `var`, nhưng kiểu của biểu thức khởi tạo khác nhau. Đây vẫn là Java có kiểm tra kiểu tĩnh.

Xem quy tắc suy luận tại [JLS §14.4.1](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.4.1).

## Kiểm tra kiểu và tạo góc nhìn cụ thể hơn

Nếu chỉ cần chức năng của `Document`, nên giữ hợp đồng tổng quát và gọi các phương thức của nó. Không cần thu hẹp kiểu chỉ để chứng minh đối tượng thuộc lớp nào.

Nếu một nhánh xử lý thực sự cần chức năng chỉ có ở `HtmlDocument`, có thể kiểm tra bằng pattern của `instanceof`:

```java
if (fromGeneral instanceof HtmlDocument html) {
    System.out.println(html.htmlOnly());
}
```

Đoạn này là mảnh minh họa đặt trong `main` của chương trình. Bên trong nhánh thành công:

- Đối tượng đã được kiểm tra phù hợp với `HtmlDocument`.
- Biến mới `html` có kiểu tĩnh `HtmlDocument`.
- `html` và `fromGeneral` tham chiếu cùng đối tượng, không có bản sao được tạo.

Dòng `report.pattern=HtmlDocument` của chương trình chứng minh `report(html)` được chọn dựa trên kiểu tĩnh của biến pattern `html`.

Kiểu tĩnh của biến gốc `fromGeneral` không tự bị đổi vĩnh viễn. Chương trình có thêm một biến với thông tin kiểu cụ thể hơn trong phạm vi nhánh.

Có thể dùng phép ép kiểu tường minh trong tình huống có bảo đảm phù hợp, nhưng ép sai sẽ có nguy cơ `ClassCastException`. Không nên dùng cast như cách buộc mọi kết quả của API tổng quát phải là một lớp con duy nhất khi hợp đồng không hứa điều đó.

## Ép kiểu đổi góc nhìn biểu thức, không đổi đối tượng

Một biểu thức như:

```java
// Mảnh minh họa; chỉ an toàn nếu general thực sự trỏ tới HtmlRenderer:
((HtmlRenderer) general).render();
```

có góc nhìn tĩnh cụ thể hơn cho đối tượng nhận lời gọi, nên chữ ký nhìn thấy có thể trả `HtmlDocument`.

Nhưng phép cast không:

- Biến một đối tượng `Renderer` thuần thành `HtmlRenderer`.
- Chạy lại constructor để tạo một lớp khác.
- Đổi kiểu khai báo của biến `general`.
- Làm một hợp đồng tổng quát luôn phù hợp với mọi yêu cầu của kiểu con.

Trong ví dụ, cast có thể thành công vì đối tượng ban đầu đúng là `HtmlRenderer`. Nếu sau đó `general` được gán `new Renderer()`, suy luận này không còn đúng.

Nếu cần tái sử dụng tính năng riêng của lớp con thường xuyên, hãy xem lại hợp đồng mà nơi gọi thực sự cần, thay vì rải các phép ép kiểu khắp mã.

## getClass chỉ trả lớp thực tế của đối tượng

Các dòng:

```java
fromGeneral.getClass().getSimpleName()
fromSpecific.getClass().getSimpleName()
```

đều in `HtmlDocument`. Đây là bằng chứng về lớp của đối tượng kết quả, không phải kiểu tĩnh của hai biến.

Không thể dùng riêng `getClass()` để xác định xem biến nguồn được khai báo là `Object`, `Document` hay `HtmlDocument`. Cùng một đối tượng có thể được nhiều biến với các kiểu tĩnh khác nhau tham chiếu.

Cũng không gọi `getClass()` trên `null`. Tham chiếu `null` có thể được giữ trong một biến kiểu tham chiếu, nhưng không có đối tượng thực tế phía sau để hỏi lớp hoặc gọi phương thức instance. Lời gọi instance qua tham chiếu `null` sẽ thất bại với `NullPointerException`.

Trong chương trình, các factory đều trả đối tượng mới nên những lệnh in lớp thực tế đều có đối tượng hợp lệ để đọc.

## Bảng đọc nhanh tại nơi gọi

| Biểu thức trong ví dụ | Kiểu tĩnh | Điều biết về giá trị thực tế |
| --- | --- | --- |
| `specific` | `HtmlRenderer` | Đối tượng HtmlRenderer đã được tạo |
| `general` | `Renderer` | Cùng renderer mà specific trỏ tới |
| `specific.render()` | `HtmlDocument` | Trả một HtmlDocument trong phần thân hiện tại |
| `general.render()` | `Document` | Chạy phần ghi đè và trả HtmlDocument trong ví dụ |
| `fromGeneral` | `Document` | Trỏ tới HtmlDocument |
| `inferred` sau `var` | `Document` | Trỏ tới HtmlDocument |
| `html` trong nhánh pattern | `HtmlDocument` | Cùng đối tượng với fromGeneral, sau kiểm tra phù hợp |

Bảng này không được dùng để suy ra rằng mọi `Renderer` trong hệ thống luôn là `HtmlRenderer`. Nó chỉ mô tả các giá trị được tạo trong chương trình cụ thể.

## Giới hạn của mô hình cần nhớ

Bài tập trung vào phương thức instance được ghi đè và nạp chồng đơn giản, không generic.

Không dùng nguyên quy tắc điều phối instance để giải thích field hoặc phương thức static; chúng có quy tắc riêng và không được ghi đè theo cùng cách.

Trong mã generic, lambda và lời gọi có suy luận kiểu, việc xác định kiểu tĩnh có thêm các quy tắc chi tiết. Nhưng vẫn phải phân biệt giai đoạn kiểm tra kiểu với lớp của đối tượng lúc chạy, thay vì cho rằng Java tự chọn mọi kiểu bằng dữ liệu thực tế.

Tương tự, phương thức của lớp con có thể luôn trả một lớp cụ thể trong phần thân hiện tại, nhưng nếu chữ ký vẫn khai báo trả kiểu cha thì phía gọi không tự nhận được cam kết kiểu hẹp hơn chỉ vì đọc được phần thân ấy.

## Lỗi phổ biến và cách tự kiểm tra

| Hiểu nhầm | Câu hỏi kiểm tra |
| --- | --- |
| Đối tượng thực tế có phương thức thì biến nào cũng gọi được | Kiểu tĩnh ở nơi gọi có thành viên đó không? |
| Override quyết định lại kiểu tĩnh của kết quả khi chạy | Chữ ký nào được nhìn thấy khi biên dịch? |
| Cùng lớp thực tế thì overload phải giống nhau | Kiểu tĩnh của từng biểu thức đối số là gì? |
| var là tự lấy kiểu từ getClass() | Kiểu của biểu thức khởi tạo lúc biên dịch là gì? |
| Cast biến đổi lớp của đối tượng | Có tạo đối tượng mới hay chỉ thêm kiểm tra/góc nhìn kiểu? |
| getClass in HtmlDocument nên biến cũng có kiểu tĩnh HtmlDocument | Biến đã được khai báo hoặc suy ra như thế nào? |
| Mọi Renderer đều tạo HtmlDocument | Hợp đồng tổng quát có thực sự cam kết điều đó không? |

Một cách đọc mã hiệu quả là ghi kiểu tĩnh ngay dưới mỗi biến/biểu thức, rồi vẽ mũi tên riêng tới đối tượng thực tế. Đừng dùng một nhãn “kiểu” chung cho cả hai.

## Thực hành kiểm chứng

1. Chạy chương trình và giải thích đủ tám dòng output.
2. Đổi `Renderer general = specific` thành `Renderer general = new Renderer()`; xác định các dòng liên quan đến kết quả của `general` thay đổi như thế nào.
3. Thử thêm `HtmlDocument invalid = general.render()` vào một bản sao nguồn để quan sát lỗi biên dịch, rồi giải thích bằng chữ ký nhìn thấy.
4. Đổi `var inferred = general.render()` thành `var inferred = specific.render()`; kiểm tra việc chọn `report`.
5. Thêm `Object broad = fromSpecific;` rồi thử `report(broad)`. Chương trình không có overload nhận `Object`, nên cần giải thích lỗi bằng kiểu tĩnh, không dựa vào lớp thực tế HtmlDocument.
6. Dùng một pattern `instanceof` phù hợp để tạo góc nhìn cụ thể, rồi kiểm tra lại lời gọi mà không dùng cast mù.

Điều cần nắm là **kiểu tĩnh quyết định lời gọi nào hợp lệ và kiểu của biểu thức kết quả; đối tượng thực tế quyết định phần thực thi phù hợp của phương thức instance được ghi đè**. Hai vai trò phối hợp để Java vừa có kiểm tra kiểu khi biên dịch vừa hỗ trợ đa hình khi chạy.
