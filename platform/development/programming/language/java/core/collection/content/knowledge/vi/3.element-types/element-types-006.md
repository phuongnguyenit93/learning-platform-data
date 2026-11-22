# Raw type, ép kiểu và ô nhiễm kiểu trong collection

Generics giúp một biến như `List<String>` diễn đạt rằng các phần tử được dùng như chuỗi. Compiler có thể từ chối nhiều thao tác sai ngay khi biên dịch:

```java
List<String> names = new ArrayList<>();
names.add("An");
```

Nếu cố thêm một `Integer` qua biến này, compiler báo lỗi. Nhưng khi collection đi qua raw type, ép kiểu không được kiểm chứng hoặc một số cách dùng mảng generic, sự bảo vệ đó có thể bị phá vỡ.

Điều khó chẩn đoán là nơi gây lỗi và nơi phát hiện lỗi có thể cách xa nhau: một đoạn mã thêm sai phần tử, đoạn khác đọc dưới kiểu đã được hứa hẹn rồi mới gặp `ClassCastException`.

Bài dùng Java 17, giải thích raw type, type erasure, các loại ép kiểu, ô nhiễm kiểu và cách xử lý ranh giới dữ liệu. Chương trình đầy đủ giữ một số cảnh báo có chủ ý để quan sát vấn đề; các đoạn được ghi rõ là lỗi biên dịch không phải lời khuyên sử dụng.

## 1. Hợp đồng kiểu phần tử bảo vệ điều gì?

Với:

```java
List<String> names = new ArrayList<>();
```

compiler biết:

- `add` cần phần tử phù hợp với `String`.
- `get` được dùng như giá trị `String`.
- Các lời gọi có thể được kiểm tra theo kiểu của biến và chữ ký phương thức.

Điều này không có nghĩa đối tượng `ArrayList` tự giữ một bộ kiểm tra `String` ở mọi vị trí trong bộ nhớ. Thông tin kiểu tại thời điểm biên dịch và kiểm tra lớp thực tế khi chạy là hai lớp cơ chế khác nhau.

Nếu mọi đường ghi vào collection tuân thủ cùng hợp đồng generic, compiler giúp duy trì sự nhất quán. Nếu có đường đi bỏ qua hợp đồng đó, một biến có khai báo đẹp vẫn có thể trỏ tới dữ liệu đã bị làm sai kiểu.

## 2. Raw type là gì và vì sao vẫn tồn tại?

**Raw type** là cách dùng một kiểu generic mà bỏ các đối số kiểu, chẳng hạn dùng `List` thay vì `List<String>`.

Đoạn minh họa:

```java
List raw = new ArrayList();
raw.add("An");
raw.add(42);
```

Raw type tồn tại chủ yếu để tương thích với mã có trước generics và các API cũ. Không nên xem nó là cách viết ngắn tương đương cho `List<Object>` hoặc `List<?>`.

Khi dùng raw type, các thành viên liên quan đến tham số kiểu được nhìn qua kiểu đã xóa trong những ngữ cảnh tương ứng. Với `List`, lời gọi thêm phần tử không còn được kiểm tra như một `List<String>`.

Compiler có thể cảnh báo:

- Dùng một raw type.
- Gọi một phương thức theo cách không thể kiểm chứng hợp đồng generic.
- Chuyển từ raw type sang kiểu có tham số mà không xác minh được.

Định nghĩa raw type nằm trong [JLS 17, mục Raw Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.8).

### 2.1. Khai báo raw chưa tự làm sai dữ liệu

Có một tham chiếu raw chưa có nghĩa đã xảy ra lỗi. Rủi ro xuất hiện khi tham chiếu đó cho phép thực hiện thao tác mà các bên đang dùng kiểu tham số không thể chấp nhận.

Ví dụ, giữ một raw alias nhưng không ghi sai kiểu chưa giống với dùng nó để chèn một số vào danh sách đang được coi là danh sách chuỗi.

Tách hai câu hỏi:

1. Có mất khả năng kiểm chứng tĩnh không?
2. Dữ liệu hoặc các giả định kiểu đã bị vi phạm chưa?

Cảnh báo thường nói về nguy cơ ở câu thứ nhất; không nên đợi có lỗi thực tế mới xử lý nó.

## 3. Phân biệt List, `List<Object>`, `List<?>` và `List<String>`

| Kiểu khai báo | Ý nghĩa | Đọc phần tử như | Thêm phần tử |
| --- | --- | --- | --- |
| `List<String>` | Biết phần tử theo hợp đồng là chuỗi | `String` | Giá trị phù hợp với `String` |
| `List<Object>` | Hợp đồng cho phép các tham chiếu đối tượng khác nhau | `Object` | Các giá trị đối tượng phù hợp |
| `List<?>` | Có một kiểu phần tử nhưng chưa biết cụ thể là gì | `Object` | Không thể thêm một giá trị khác null tùy ý theo kiểm tra kiểu |
| Raw `List` | Dùng kiểu generic mà bỏ đối số kiểu | Thường là kiểu đã xóa, ở đây là `Object` | Có thể viết thao tác không được kiểm chứng generic |

Các thao tác sửa còn phải được lớp triển khai hỗ trợ. Bảng nói về khả năng theo kiểu, không hứa một danh sách bất kỳ sẽ cho thêm.

### 3.1. `List<Object>` có thể chứa nhiều kiểu một cách có chủ đích

Đoạn minh họa:

```java
List<Object> values = new ArrayList<>();
values.add("An");
values.add(42);
```

Danh sách chứa nhiều kiểu không tự đồng nghĩa ô nhiễm kiểu. Hợp đồng `List<Object>` vốn cho phép các giá trị đó; bên đọc nhận `Object` và phải quyết định xử lý phù hợp.

Ô nhiễm kiểu liên quan tới việc phá vỡ một giả định kiểu đã được khai báo, không phải cứ thấy hai lớp phần tử khác nhau là kết luận có ô nhiễm.

### 3.2. `List<String>` không phải `List<Object>`

Đoạn dưới không biên dịch:

```java
List<String> names = new ArrayList<>();
List<Object> objects = names;
```

Nếu phép gán này được cho phép, bên giữ `objects` có thể thêm `Integer`, khiến bên giữ `names` đọc sai kiểu.

Generics không có quan hệ kiểu con theo cách đó. Dùng `List<?>` nếu chỉ cần nhận một danh sách có kiểu phần tử chưa biết:

```java
List<?> unknown = names;
```

### 3.3. `List<?>` không phải danh sách bất biến

Không thể gọi `unknown.add("text")` chỉ vì chuỗi là một đối tượng: kiểu phần tử thực sự có thể là `Integer`.

Tuy nhiên, `List<?>` không cấm mọi thay đổi. Chẳng hạn, xóa hoặc `clear` có thể hợp lệ theo kiểu và được thực hiện nếu lớp triển khai hỗ trợ.

`null` có thể phù hợp theo kiểm tra kiểu với một tham chiếu phần tử chưa biết, nhưng collection thực tế có thể cấm `null` hoặc cấm thêm. Không dùng wildcard để suy ra khả năng sửa hay chính sách `null`.

## 4. Ô nhiễm kiểu trong collection

**Ô nhiễm kiểu (heap pollution)** xảy ra khi một biến có kiểu tham số tham chiếu đến đối tượng không đáp ứng kiểu tham số được giả định. Trong collection, biểu hiện thường gặp là một danh sách đang được dùng như `List<String>` lại chứa phần tử không phải chuỗi do một đường ghi không an toàn.

Ví dụ:

```java
List<String> names = new ArrayList<>();
List raw = names;
raw.add(42);
```

Đồ thị tham chiếu:

```text
names, được nhìn như List<String> ----+
                                    |
                                    v
                              cùng ArrayList
                                    |
raw, được nhìn như List -------------+
                                    |
                                    v
                               phần tử Integer 42
```

Không có hai danh sách. Phép gán chỉ tạo thêm một tham chiếu tới cùng đối tượng, với khả năng kiểm tra kiểu khác ở phía mã nguồn.

Lời gọi qua raw type có thể chèn số vào vùng dữ liệu mà bên khác đang tin là danh sách chuỗi. Khái niệm được quy định trong [JLS 17, Heap Pollution](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.12.2).

### 4.1. Lỗi thường xuất hiện muộn

Đoạn tiếp theo:

```java
String first = names.get(0);
```

gặp `ClassCastException` khi phần tử thực tế là `Integer`.

Nơi đọc có vẻ hoàn toàn bình thường: biến được khai báo `List<String>`, nên lập trình viên không viết một cast tường minh nào. Nhưng compiler cần thực hiện kiểm tra phù hợp khi đưa kết quả đã xóa kiểu về `String`.

Vì vậy, stack trace ở `get` chưa chắc chỉ ra nơi gốc của lỗi. Cần truy ngược các đường tạo, trả về, alias và ghi vào collection.

### 4.2. Không phải mọi thao tác đều phát hiện ngay

Các thao tác như `size()` không cần dùng phần tử như `String`. Chúng có thể tiếp tục hoạt động dù danh sách đã bị sai kiểu.

Ngay cả đọc phần tử qua một tham chiếu chỉ yêu cầu `Object` cũng chưa nhất thiết buộc kiểm tra như chuỗi.

Không dùng việc “in được”, “đếm được” hay “đã đọc vài phần tử đầu” làm bằng chứng toàn collection đáp ứng kiểu mong muốn.

## 5. Type erasure giải thích điều gì?

Java triển khai generics chủ yếu bằng **xóa kiểu (type erasure)**.

Ở mức cần cho bài này:

- Hai `ArrayList` tạo với đối số kiểu `String` và `Integer` không trở thành hai lớp runtime chuyên biệt khác nhau chỉ vì đối số generic khác.
- Với `List<E>` không có cận cụ thể hơn, kiểu đã xóa liên quan đến phần tử là `Object`.
- Compiler kiểm tra kiểu ở mã nguồn và có thể chèn cast khi cần để khôi phục cách sử dụng theo kiểu đã khai báo.

Có thể hình dung lời đọc:

```java
String value = names.get(0);
```

ở mức cơ chế gần với “đọc đối tượng rồi kiểm tra dùng như `String`”. Đây là mô hình để hiểu, không phải yêu cầu mọi compiler luôn sinh bytecode giống hệt nhau.

### 5.1. Không nói quá rằng mọi thông tin generic đều biến mất

Chữ ký generic của khai báo lớp hoặc phương thức có thể tồn tại trong metadata và được phản chiếu ở những ngữ cảnh phù hợp.

Điểm cần phân biệt là các tham số kiểu của một biến như `List<String>` không tự biến thành một kiểm tra sâu mọi phần tử trên từng đối tượng danh sách thông thường.

Biết có thể đọc metadata của khai báo không có nghĩa đã xác minh được danh sách do mã ngoài đưa vào chỉ chứa chuỗi.

### 5.2. Bound và erasure không phải luôn là Object

Một tham số kiểu có cận có thể được xóa về cận tương ứng. Bài dùng `List<E>` để giải thích vì trường hợp này dễ quan sát, không đưa ra quy tắc “mọi generic luôn xóa thành Object” cho toàn bộ Java.

Xem [JLS 17, Type Erasure](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.6).

## 6. Ép kiểu collection kiểm tra được đến đâu?

### 6.1. Cast tham chiếu không chuyển đổi các phần tử

Giả sử có:

```java
Object candidate = List.of(1, 2, 3);
```

Ép `candidate` thành `List<String>` không biến các số thành chuỗi `"1"`, `"2"`, `"3"`. Nó chỉ yêu cầu nhìn cùng tham chiếu theo một kiểu khác, kèm những kiểm tra runtime mà hệ thống kiểu có thể thực hiện.

Nếu muốn chuyển đổi giá trị, cần thao tác chuyển đổi rõ ràng, chẳng hạn ánh xạ từng số sang biểu diễn chuỗi. Cast không thay cho chuyển đổi dữ liệu.

### 6.2. Checked cast ở lớp bên ngoài

Một cast sang một kiểu runtime có thể kiểm tra được sẽ xác minh lớp hoặc interface tương ứng.

Nếu đối tượng thực tế không phải list, cast sang `List` có thể ném `ClassCastException` ngay.

Nếu đối tượng là list chứa số, kiểm tra “có phải List không?” có thể qua được. Nhưng điều đó chưa kiểm tra phần tử bên trong là chuỗi.

### 6.3. Unchecked cast

Đoạn minh họa cố ý không an toàn:

```java
Object candidate = List.of(1, 2, 3);
List<String> names = (List<String>) candidate;
```

Compiler cảnh báo vì không thể kiểm chứng đầy đủ đối số generic `String` ở cast này. Lớp ngoài có thể được kiểm tra là `List`, nhưng thành phần generic vẫn không được chứng minh.

Đừng diễn giải “unchecked” thành “không có bất kỳ kiểm tra runtime nào”. Một cast có thể còn kiểm tra lớp ngoài nhưng không đủ để chứng minh toàn bộ kiểu tham số.

Nếu sau đó đọc phần tử như `String`, mới có thể gặp lỗi ở vị trí đọc.

### 6.4. Unchecked conversion không nhất thiết có cú pháp cast

Ví dụ:

```java
List raw = legacyResult();
List<String> names = raw;
```

Lời gán thứ hai có thể tạo cảnh báo unchecked conversion. Không có dấu ngoặc cast nhưng vẫn có một lời hứa về kiểu phần tử chưa được kiểm chứng.

Hàm `legacyResult` ở đây chỉ là ký hiệu cho API cũ, không phải phương thức được định nghĩa trong chương trình mẫu.

### 6.5. Tập trung vào nguồn bằng chứng

Muốn tin `List<String>`, cần một trong các cơ sở phù hợp:

- Luồng dữ liệu được compiler kiểm tra xuyên suốt.
- Một API có hợp đồng đáng tin và được triển khai đúng.
- Kiểm tra từng phần tử cùng việc kiểm soát các đường ghi về sau.
- Sao chép sau kiểm tra vào một cấu trúc mới có kiểu rõ ràng.

Một cast hoặc một annotation chỉ làm mã bớt cảnh báo không tự bổ sung bằng chứng này. Các loại chuyển đổi được mô tả trong [JLS 17, Conversions and Contexts](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html).

## 7. Kiểm tra dữ liệu chưa rõ kiểu bằng wildcard

### 7.1. Kiểm tra lớp ngoài trước

Khi đầu vào có kiểu `Object`, có thể kiểm tra:

```java
if (candidate instanceof List<?> items) {
    for (Object item : items) {
        // Xu ly theo kieu thuc te cua item.
    }
}
```

Khối trên là đoạn minh họa chưa có xử lý nghiệp vụ.

Với `Object` chưa rõ kiểu, không thể dùng `instanceof List<String>` như một phép kiểm tra sâu hợp lệ để chứng minh mọi phần tử là chuỗi. Kiểu `List<?>` thích hợp để kiểm tra hình dạng ngoài mà không hứa một kiểu phần tử chưa được chứng minh.

Không tổng quát thành “Java không bao giờ cho xuất hiện kiểu có tham số ở phía instanceof” trong mọi ngữ cảnh. Quy tắc phụ thuộc khả năng kiểm tra và kiểu đã biết; bài này đang nói về đối tượng đầu vào hoàn toàn chưa biết.

### 7.2. Kiểm tra từng phần tử rồi tạo bản sao

Một hàm có chính sách chỉ nhận chuỗi không null:

```java
static List<String> copyStrings(Collection<?> source) {
    List<String> result = new ArrayList<>();
    for (Object value : source) {
        if (!(value instanceof String text)) {
            throw new IllegalArgumentException("Expected non-null String");
        }
        result.add(text);
    }
    return result;
}
```

Hàm trên cần đặt trong một lớp cùng các import phù hợp. Chương trình đầy đủ bên dưới có phiên bản bổ sung thông báo kiểu thực tế.

Cơ chế:

1. Nhận đầu vào mà không hứa trước kiểu phần tử cụ thể.
2. Đọc từng phần tử như `Object`.
3. Kiểm tra bằng `instanceof String`.
4. Chỉ thêm giá trị đã được chứng minh vào `List<String>` mới.
5. Trả kết quả không chia sẻ cấu trúc danh sách với đầu vào.

Nếu kiểm tra lỗi ở giữa, danh sách nguồn không bị sửa bởi hàm. Bản kết quả đang xây dựng chưa được trả ra.

Chính sách `null` là chủ ý: `instanceof String` trả `false` với `null`, nên hàm từ chối nó. Nếu ứng dụng chấp nhận `null`, cần thiết kế nhánh tương ứng rõ ràng.

### 7.3. Vì sao kiểm tra rồi cast cùng đối tượng vẫn có thể rủi ro?

Ngay cả khi vừa duyệt thấy mọi phần tử là chuỗi, nếu bên khác vẫn có raw alias tới chính danh sách đó, họ có thể chèn giá trị khác sau bước kiểm tra.

Sao chép vào danh sách mới giúp tách cấu trúc và đường ghi, nhưng không giải quyết mọi tình huống:

- Nguồn bị sửa đồng thời trong khi sao chép cần cơ chế phù hợp.
- Phần tử có thể thay đổi vẫn có thể được chia sẻ.
- Quy tắc kiểm tra cần khớp yêu cầu nghiệp vụ, không chỉ lớp Java.

Với ví dụ chuỗi, phần tử `String` bất biến giúp ranh giới dễ quản lý hơn.

### 7.4. Generic lồng cần kiểm tra từng tầng

Với yêu cầu `List<List<String>>`, biết mỗi phần tử là `List` chưa chứng minh các phần tử bên trong là `String`.

Tương tự, `Map<String, List<Integer>>` cần xét kiểu khóa, kiểu collection giá trị và kiểu phần tử trong mỗi danh sách.

Một `Class<List>` hoặc `List.class` không mang đầy đủ điều kiện kiểm tra `List<String>`. Cần kiểm tra có cấu trúc hoặc dùng cơ chế ánh xạ dữ liệu có hợp đồng rõ ràng.

## 8. Collections.checkedList: phát hiện một số lỗi tại nơi ghi

Java cung cấp các view kiểm tra kiểu động, ví dụ:

```java
List<String> backing = new ArrayList<>();
List<String> checked = Collections.checkedList(backing, String.class);
```

Nếu một đoạn mã raw cố chèn `Integer` **qua checked view**, nó bị từ chối bằng `ClassCastException` tại lần chèn.

Điều này đưa điểm phát hiện gần nơi gây lỗi hơn so với chờ một bên khác đọc phần tử như chuỗi.

### 8.1. Không phải cách sửa mọi raw type

Dùng wrapper không phải lý do tiếp tục thiết kế API mới bằng raw type. Nó là một công cụ bảo vệ động hoặc chẩn đoán ở ranh giới phù hợp.

Khi có thể sửa kiểu khai báo và chữ ký phương thức, đó thường là cách tốt hơn để compiler kiểm tra luồng dữ liệu.

### 8.2. Không kiểm tra toàn bộ dữ liệu đã có khi tạo view

Tạo một checked view không nên được coi là thủ tục xác minh sâu hoặc làm sạch mọi phần tử đang có trong danh sách nền.

Nếu nguồn đã sai kiểu, cần kiểm tra dữ liệu hoặc tạo bản sao hợp lệ thay vì chỉ bọc lại và tin rằng mọi thứ đã được sửa.

### 8.3. Tham chiếu đi thẳng vào backing list vẫn có thể vượt qua wrapper

Nếu bên khác giữ `backing` và dùng một raw alias để ghi thẳng vào nó, họ không đi qua kiểm tra của `checked`.

View và list nền chia sẻ dữ liệu. Tất cả đường ghi liên quan phải được kiểm soát thì wrapper mới cung cấp ranh giới có ý nghĩa.

### 8.4. Chỉ kiểm tra kiểu runtime được cung cấp

`String.class` đủ để kiểm tra một phần tử có phải chuỗi trong ví dụ này. Với kiểu generic lồng, cung cấp lớp ngoài không tự kiểm tra đối số kiểu bên trong.

Wrapper cũng không phải deep copy, cơ chế bất biến hay cơ chế đồng bộ giữa các luồng. Xem [Collections.checkedList Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#checkedList(java.util.List,java.lang.Class)).

## 9. Bản sao và view không tự khôi phục tính đúng kiểu

### 9.1. Sao chép một nguồn đã bị khai báo sai

Nếu biến `names` mang kiểu `List<String>` nhưng dữ liệu đã bị ô nhiễm, viết:

```java
List<String> copy = new ArrayList<>(names);
```

không phải một phép xác minh từng phần tử là chuỗi. Compiler đang tin vào kiểu của nguồn; constructor sao chép cũng không nhận `String.class` để làm kiểm tra đó.

Bản mới có thể tiếp tục mang dữ liệu không phù hợp và lỗi chỉ lộ khi đọc theo kiểu cụ thể.

### 9.2. Unmodifiable không có nghĩa đã xác minh kiểu

Bọc nguồn bằng view không cho sửa chỉ hạn chế những thao tác sửa qua view. Nó không biến một `Integer` đã chèn sai thành `String`.

`List.copyOf` cũng không phải bộ xác minh sâu generic theo tên kiểu mà caller mong muốn. Những kiểm tra khác của API, chẳng hạn chính sách `null`, không đồng nghĩa đã kiểm tra mọi điều kiện phần tử của ứng dụng.

### 9.3. Kiểm tra đúng lớp chưa đủ đúng nghiệp vụ

Một danh sách toàn `String` vẫn có thể chứa mã rỗng, email sai định dạng hoặc giá trị ngoài miền chấp nhận.

Cần phân biệt:

- Đúng kiểu Java.
- Đúng cấu trúc dữ liệu.
- Đúng ràng buộc nghiệp vụ.

Không dùng một cast generic thay cho cả ba tầng kiểm tra.

## 10. Generic varargs và mảng: một con đường gây ô nhiễm khác

Raw type là một nguồn thường gặp, nhưng không phải nguồn duy nhất. Mảng và tham số varargs với kiểu generic cũng có thể làm phá vỡ hợp đồng.

### 10.1. Vì sao mảng là điểm nhạy cảm?

Mảng có thông tin kiểu thành phần runtime và có quan hệ kiểu con theo cách khác generics. Trong khi đó, `List<String>` không được biểu diễn như một lớp danh sách chuyên biệt runtime theo `String`.

Java không cho tạo trực tiếp:

```java
new List<String>[2]
```

Đây là ví dụ không biên dịch. Không dùng cast vòng qua raw array như một cách tổng quát để tạo mảng generic an toàn.

### 10.2. Ví dụ varargs không an toàn

Đoạn minh họa cần đặt trong một lớp:

```java
static String unsafeVarargs(List<String>... groups) {
    Object[] exposed = groups;
    exposed[0] = List.of(123);
    return groups[0].get(0);
}
```

Diễn biến:

1. Tham số varargs được dùng qua một mảng có kiểu thành phần runtime không kiểm tra được đối số `String` của `List`.
2. Mảng đó được nhìn như `Object[]`.
3. Một `List<Integer>` được đặt vào vị trí mà phía mã nguồn đang coi là `List<String>`.
4. Đọc phần tử đầu như `String` gây `ClassCastException`.

Ở đây không có một raw `List` trong thân hàm, nhưng vẫn có khả năng ô nhiễm kiểu qua mảng và các alias.

### 10.3. @SafeVarargs là lời xác nhận của tác giả

Annotation này không chèn thêm một bộ kiểm tra kiểu runtime và không làm một thân hàm nguy hiểm tự trở nên an toàn.

Không gắn `@SafeVarargs` vào ví dụ trên chỉ để tắt cảnh báo. Tác giả phải chứng minh cách dùng varargs không gây ô nhiễm, đồng thời tuân thủ những vị trí khai báo được phép dùng annotation.

Một mẫu có thể an toàn khi chỉ đọc các danh sách đầu vào và chép phần tử sang kết quả mới:

```java
@SafeVarargs
static <T> List<T> concatenate(List<? extends T>... groups) {
    List<T> result = new ArrayList<>();
    for (List<? extends T> group : groups) {
        result.addAll(group);
    }
    return result;
}
```

Hàm không ghi một danh sách không phù hợp vào mảng varargs hoặc đưa chính mảng đó ra ngoài. Lời xác nhận vẫn cần xét toàn bộ mã thực tế, không chỉ hình dạng chữ ký.

Xem [SafeVarargs Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/SafeVarargs.html).

## 11. Cảnh báo compiler là một phần của bằng chứng

### 11.1. Bật cảnh báo liên quan

Lệnh thường dùng khi xem xét loại mã này:

```shell
javac --release 17 -Xlint:rawtypes,unchecked Example.java
```

- `rawtypes` giúp thấy nơi bỏ đối số kiểu.
- `unchecked` giúp thấy nơi compiler không kiểm chứng đầy đủ chuyển đổi, lời gọi hoặc một số trường hợp generic liên quan.

Cảnh báo không nhất thiết làm biên dịch thất bại. Vì vậy, “build thành công” chưa chứng minh không có nguy cơ kiểu.

### 11.2. Không đồng nhất mọi cảnh báo với một lỗi runtime chắc chắn

Một phép cast có thể đúng nhờ một bất biến mà compiler không diễn đạt được. Ngược lại, một cast có thể sai nhưng chưa gặp dữ liệu làm nó lộ lỗi.

Mục tiêu là tìm bằng chứng cho tính đúng, không chỉ làm cảnh báo biến mất.

### 11.3. SuppressWarnings không thêm bảo vệ

`@SuppressWarnings("unchecked")` chỉ tác động cách báo cảnh báo; nó không kiểm tra các phần tử và không đổi kết quả runtime.

Nếu thật sự cần dùng:

1. Đặt ở phạm vi nhỏ nhất chứa thao tác không thể kiểm chứng.
2. Giải thích bất biến nào làm thao tác đó an toàn.
3. Giữ các đường ghi và quyền sở hữu dữ liệu phù hợp bất biến.
4. Có kiểm thử mang ý nghĩa kiểm tra bất biến.

Không tắt cảnh báo cho cả module để che một ranh giới API cũ chưa được phân tích.

### 11.4. Chú ý cảnh báo trong thư viện và ranh giới khác

Mã caller không có cast nguy hiểm không đủ chứng minh toàn bộ chương trình không bị ô nhiễm. Một thư viện, API cũ hoặc cơ chế ngoài kiểm tra generic có thể trả một đối tượng với lời hứa kiểu không đúng.

Khi lỗi xuất hiện ở một dòng đọc đơn giản, phải xét cả nguồn dữ liệu và những nơi khác giữ alias.

## 12. Chương trình Java hoàn chỉnh

Chương trình sau cố ý tạo một số tình huống không an toàn để so sánh điểm phát hiện. Không dùng các hàm `legacyAdd` hoặc `unsafeVarargs` làm mẫu API mới.

Lưu vào tệp `CollectionTypePollutionDemo.java`:

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.Collections;
import java.util.List;

public class CollectionTypePollutionDemo {
    private static void legacyAdd(List list, Object value) {
        list.add(value);
    }

    private static List<String> copyStrings(Collection<?> source) {
        List<String> result = new ArrayList<>();
        for (Object value : source) {
            if (!(value instanceof String text)) {
                String actualType = value == null
                        ? "null" : value.getClass().getSimpleName();
                throw new IllegalArgumentException(
                        "Expected String, found " + actualType);
            }
            result.add(text);
        }
        return result;
    }

    private static String unsafeVarargs(List<String>... groups) {
        Object[] exposed = groups;
        exposed[0] = List.of(123);
        return groups[0].get(0);
    }

    public static void main(String[] args) {
        List<String> names = new ArrayList<>();
        legacyAdd(names, 42);
        System.out.println("size after legacy write: " + names.size());

        try {
            String first = names.get(0);
            System.out.println("unexpected string: " + first);
        } catch (ClassCastException ex) {
            System.out.println("typed read: ClassCastException");
        }

        List<String> backing = new ArrayList<>();
        List<String> checked = Collections.checkedList(backing, String.class);

        try {
            legacyAdd(checked, 99);
        } catch (ClassCastException ex) {
            System.out.println("checked write: ClassCastException");
        }
        System.out.println("checked size after rejected write: "
                + checked.size());

        legacyAdd(backing, 99);
        System.out.println("backing bypass size: " + checked.size());
        try {
            String first = checked.get(0);
            System.out.println("unexpected checked string: " + first);
        } catch (ClassCastException ex) {
            System.out.println("bypass typed read: ClassCastException");
        }

        List<String> valid = copyStrings(List.of("An", "Binh"));
        System.out.println("validated copy: " + valid);

        Object candidate = List.of("An", 7);
        if (candidate instanceof List<?> unknown) {
            System.out.println("runtime shape is List: true");
            try {
                copyStrings(unknown);
            } catch (IllegalArgumentException ex) {
                System.out.println("validation: " + ex.getMessage());
            }
        }

        try {
            unsafeVarargs(List.of("safe"));
        } catch (ClassCastException ex) {
            System.out.println("varargs typed read: ClassCastException");
        }
    }
}
```

Biên dịch:

```shell
javac --release 17 -Xlint:rawtypes,unchecked CollectionTypePollutionDemo.java
```

Compiler phát cảnh báo về raw type, lời gọi không được kiểm chứng và generic varargs. Các cảnh báo này là phần cố ý của thí nghiệm. Câu chữ, đường dẫn và số dòng chẩn đoán có thể khác theo JDK.

Sau khi biên dịch thành công, chạy:

```shell
java CollectionTypePollutionDemo
```

Stdout chuẩn:

```text
size after legacy write: 1
typed read: ClassCastException
checked write: ClassCastException
checked size after rejected write: 0
backing bypass size: 1
bypass typed read: ClassCastException
validated copy: [An, Binh]
runtime shape is List: true
validation: Expected String, found Integer
varargs typed read: ClassCastException
```

### 12.1. Lỗi thứ nhất được phát hiện tại lúc đọc

`legacyAdd(names, 42)` nhận raw `List`, nên có thể thêm phần tử không phù hợp với lời hứa của biến `names`.

`size()` vẫn trả 1. Khi lấy phần tử để gán sang `String`, mới có `ClassCastException`.

### 12.2. Checked view đưa lỗi về lúc ghi

Lần ghi số qua `checked` bị từ chối. Kích thước vẫn 0 vì thao tác thêm đó không được chấp nhận.

Điều này giúp phát hiện nơi gây lỗi sớm hơn; nó không làm raw API trở thành một thiết kế được khuyến nghị.

### 12.3. Backing alias có thể đi vòng

Lần ghi thẳng qua `backing` không đi qua wrapper. `checked.size()` nhìn thấy phần tử mới vì view dùng cùng dữ liệu.

Khi caller đọc phần tử như chuỗi, tiếp tục có lỗi. Ví dụ minh họa giới hạn của wrapper nếu các đường ghi không được kiểm soát.

### 12.4. Kiểm tra từng phần tử tạo kết quả mới hợp lệ

`copyStrings` nhận dữ liệu qua `Collection<?>`, kiểm tra từng phần tử rồi xây `List<String>` mới.

Nguồn hợp lệ cho kết quả `[An, Binh]`. Nguồn có chuỗi và số bị từ chối bằng thông báo do ứng dụng chủ động tạo, thay vì để lỗi cast lộ muộn tại nơi sử dụng.

### 12.5. Varargs cho thấy nguồn lỗi khác raw List

Hàm cuối làm sai kiểu của một vị trí trong mảng varargs rồi đọc theo giả định `List<String>`. Nó minh họa vì sao cần xem xét cả mảng và đường alias, không chỉ tìm từ khóa raw type.

Các khối bắt ngoại lệ giúp chương trình chạy hết các thí nghiệm. Trong hệ thống thực tế, cách xử lý đúng là bảo vệ ranh giới dữ liệu và hợp đồng, không phải bắt `ClassCastException` sau mỗi lần đọc collection.

## 13. Làm việc với API cũ hoặc dữ liệu ngoài

### 13.1. Cô lập ranh giới chưa rõ kiểu

Nếu một thư viện trả raw collection, không truyền nó sâu vào nhiều tầng rồi cast ở từng nơi.

Nên có một ranh giới:

```text
API cu hoac du lieu chua ro kieu
        |
        v
kiem tra cau truc va phan tu
        |
        v
collection co kieu ro rang cua ung dung
```

Sau ranh giới, các phần còn lại dùng kiểu generic bình thường và không cần lặp lại cast.

### 13.2. Chọn hành vi với phần tử sai

Có thể:

- Từ chối toàn bộ dữ liệu và báo lỗi.
- Thu thập lỗi từng vị trí để người dùng sửa.
- Chuyển đổi một số dạng dữ liệu theo quy tắc rõ ràng.
- Bỏ phần tử không hợp lệ nếu đó thật sự là yêu cầu đã được xác định.

Không lặng lẽ đổi mọi đối tượng thành chuỗi bằng `toString()` chỉ để đáp ứng `List<String>`. Kết quả có thể không mang ý nghĩa dữ liệu mà ứng dụng cần.

### 13.3. Bảo toàn nguồn khi kiểm tra thất bại

Kiểm tra vào một kết quả mới giúp tránh sửa dữ liệu gốc trong quá trình xác minh.

Nếu nguồn hoặc phần tử có thể bị thay đổi đồng thời, cần tổ chức sở hữu, bản chụp hoặc đồng bộ phù hợp; vòng lặp kiểm tra không tự tạo giao dịch trên dữ liệu chia sẻ.

### 13.4. Đừng dùng generic để che kiểu miền chưa rõ

Nếu dữ liệu thực sự có nhiều loại phần tử hợp lệ, nên diễn đạt rõ bằng `List<Object>`, một kiểu chung có ý nghĩa hoặc mô hình dữ liệu phân biệt từng biến thể.

Gắn `List<String>` lên dữ liệu không thuần chuỗi rồi cast không làm mô hình trở nên chính xác hơn.

## 14. Trình tự chẩn đoán ClassCastException trong collection

Khi lỗi xảy ra ở `String name = names.get(i)` hoặc trong `for (String name : names)`, nên kiểm tra:

1. Phần tử thực tế tại vị trí lỗi có lớp gì?
2. Biến có kiểu nào tại thời điểm biên dịch?
3. Collection được tạo hoặc trả về từ đâu?
4. Có raw parameter, raw return type hoặc unchecked cast không?
5. Có alias khác đang ghi vào cùng đối tượng không?
6. Có mảng generic, varargs hoặc wrapper được dùng sai không?
7. Có dùng bản sao hoặc unmodifiable view như một phép xác minh kiểu không?
8. Điểm chuyển từ dữ liệu chưa rõ kiểu sang kiểu miền đã có kiểm tra thực sự chưa?
9. Nếu có suppress cảnh báo, bất biến được ghi ở đó còn đúng không?
10. Cần sửa nguồn hợp đồng hay chỉ sửa một chỗ đọc?

Không thêm cast ở dòng đang lỗi như phản xạ đầu tiên. Cast bổ sung không biến một `Integer` thành `String` và thường chỉ chuyển chỗ báo lỗi.

## 15. Bài tập tự kiểm chứng

### Bài 1: Chọn đúng kiểu khai báo

Có ba nhu cầu:

- Một danh sách chắc chắn gồm tên dạng chuỗi.
- Một danh sách có thể chứa nhiều loại giá trị hợp lệ.
- Một hàm chỉ cần xem kích thước và đọc từng phần tử chưa biết kiểu.

Chọn lần lượt `List<String>`, `List<Object>` và `List<?>`. Giải thích vì sao raw `List` không phải lựa chọn mặc định cho nhu cầu thứ ba.

### Bài 2: Dự đoán điểm phát hiện lỗi

Tạo `List<String>`, tạo raw alias, chèn `Integer`, sau đó:

- Gọi `size()`.
- Đọc qua raw alias vào biến `Object`.
- Đọc qua biến kiểu tham số vào biến `String`.

Dự đoán thao tác nào cần kiểm tra như chuỗi và giải thích vì sao lỗi không xuất hiện ngay ở mọi thao tác.

### Bài 3: Kiểm tra nguồn hỗn hợp

Viết hàm tạo `List<String>` mới từ `Collection<?>` theo chính sách:

- Chỉ chấp nhận chuỗi không null.
- Nếu gặp phần tử sai, báo vị trí cùng kiểu thực tế.
- Không sửa nguồn.
- Không dùng unchecked cast.

Kiểm tra nguồn rỗng, toàn chuỗi, có số ở cuối và có `null`.

### Bài 4: Chứng minh giới hạn của checkedList

Tạo list nền và checked view. Thử ghi sai kiểu qua view, rồi thử qua raw alias của list nền.

Giải thích vì sao chỉ lời gọi qua view được bảo vệ và vì sao cần kiểm soát quyền sở hữu backing collection.

### Bài 5: Kiểm tra generic lồng

Nhận một `Object` được kỳ vọng là danh sách các danh sách chuỗi. Viết kiểm tra từng tầng và tạo cấu trúc kết quả mới.

Không dùng `List.class` như bằng chứng đủ cho toàn bộ `List<List<String>>`.

### Bài 6: Rà soát một suppress cảnh báo

Tìm một đoạn giả định cần `@SuppressWarnings("unchecked")`. Ghi rõ:

- Compiler không kiểm chứng được điều gì?
- Bằng chứng nào từ chương trình làm phép chuyển đổi an toàn?
- Ai còn có thể ghi vào dữ liệu?
- Cần kiểm thử gì nếu bất biến bị phá vỡ?

Nếu không trả lời được, chưa có cơ sở để coi việc tắt cảnh báo là xử lý xong.

## 16. Những kết luận cần tránh

- “Raw List chính là `List<Object>` viết ngắn.”
- “List<?> nghĩa là không được thay đổi bất kỳ điều gì.”
- “Danh sách có nhiều lớp phần tử thì luôn là heap pollution.”
- “Cast sang `List<String>` sẽ kiểm tra từng phần tử.”
- “Không viết cast tại get thì không thể có ClassCastException.”
- “Bọc unmodifiable hoặc copyOf là làm sạch dữ liệu sai kiểu.”
- “checkedList bảo vệ cả những đường ghi đi thẳng vào backing list.”
- “SafeVarargs hoặc SuppressWarnings làm thân hàm tự an toàn.”
- “Không có cảnh báo ở caller thì nguồn thư viện chắc chắn đúng kiểu.”
- “Thêm một cast nữa là cách sửa giá trị có kiểu không phù hợp.”

Mục tiêu là giữ lời hứa về kiểu phần tử có căn cứ: dùng generics xuyên suốt nơi có thể, đặt kiểm tra rõ ràng ở ranh giới chưa rõ kiểu, kiểm soát các đường ghi và coi cảnh báo chưa được giải thích là một phần công việc còn phải phân tích.
