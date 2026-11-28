# mapMulti và phép biến đổi một phần tử thành không, một hoặc nhiều phần tử

Từ Java 16, Stream API có phương thức `mapMulti` để biến đổi mỗi phần tử đầu vào thành **không, một hoặc nhiều phần tử đầu ra**. Phương thức này hữu ích khi logic biến đổi cần rẽ nhánh hoặc duyệt một tập hợp con bên trong từng phần tử. Thay vì phải tạo một Stream trung gian cho mỗi phần tử như cách thường làm với `flatMap`, ta nhận một Consumer và gọi `accept` mỗi khi muốn phát ra kết quả.

`mapMulti` vẫn là một phần của Stream API trong các phiên bản Java hiện đại. Các ví dụ dưới đây dùng cú pháp Java 16 trở lên và tập trung vào cách dùng ổn định.

## 1. Ý tưởng cốt lõi

Với mỗi phần tử nguồn được pipeline xử lý, hàm mapper được gọi một lần. Mapper nhận:

1. Phần tử đầu vào hiện tại.
2. Một Consumer để gửi các phần tử kết quả xuống phần còn lại của pipeline.

Số lần gọi Consumer quyết định số phần tử được tạo ra:

| Số lần gọi `accept` | Kết quả của phần tử đầu vào |
|---|---|
| Không gọi | Không tạo phần tử đầu ra, tương tự loại bỏ phần tử |
| Gọi một lần | Tạo một phần tử đầu ra |
| Gọi nhiều lần | Tạo nhiều phần tử đầu ra |

Ví dụ, một đơn hàng có thể không có sản phẩm hợp lệ, có một sản phẩm hoặc có nhiều sản phẩm. Mapper có thể duyệt các dòng hàng và chỉ phát ra những dòng thỏa điều kiện.

Điểm quan trọng là Consumer được dùng ngay trong lần gọi mapper tương ứng. Hãy phát các kết quả trong callback; không lưu Consumer để gọi về sau hoặc chuyển việc gọi nó sang một tác vụ bất đồng bộ.

## 2. Cú pháp và các phương thức liên quan

Phương thức tổng quát trên `Stream<T>` có dạng:

```java
<R> Stream<R> mapMulti(
    BiConsumer<? super T, ? super Consumer<R>> mapper
)
```

Trong đó:

- `T` là kiểu phần tử của Stream nguồn.
- `R` là kiểu phần tử được phát ra.
- Tham số thứ nhất của mapper là phần tử nguồn hiện tại.
- Tham số thứ hai là Consumer nhận các phần tử kiểu `R`.
- Mapper có thể gọi Consumer không lần nào, một lần hoặc nhiều lần.

Ví dụ khung:

```java
Stream<String> result = source.<String>mapMulti((element, emit) -> {
    if (conditionA(element)) {
        emit.accept(convertA(element));
    }

    if (conditionB(element)) {
        emit.accept(convertB(element));
    }
});
```

Cú pháp `.<String>mapMulti` chỉ rõ kiểu đầu ra. Có thể bỏ phần chỉ định kiểu khi trình biên dịch suy luận được kiểu `R` từ ngữ cảnh.

Ngoài phiên bản trả về `Stream<R>`, Stream API còn có các phương thức chuyên biệt cho kiểu nguyên thủy:

- `mapMultiToInt` trả về `IntStream`.
- `mapMultiToLong` trả về `LongStream`.
- `mapMultiToDouble` trả về `DoubleStream`.

Ví dụ chữ ký của phiên bản int:

```java
IntStream mapMultiToInt(
    BiConsumer<? super T, ? super IntConsumer> mapper
)
```

Các phiên bản này hữu ích khi kết quả là số nguyên thủy và ta muốn tiếp tục dùng các phép toán như `sum`, `average` hoặc `summaryStatistics` mà không phải chuyển qua `Stream<Integer>`, `Stream<Long>` hay `Stream<Double>`.

## 3. Ví dụ: một phần tử tạo ra không, một hoặc nhiều kết quả

Giả sử mỗi người dùng có thể có địa chỉ email chính và email dự phòng. Ta muốn lấy tất cả địa chỉ hợp lệ. Mỗi người dùng có thể đóng góp từ không đến hai địa chỉ:

```java
import java.util.List;

record User(String email, String backupEmail) {}

List<User> users = List.of(
    new User("an@example.com", "an.backup@example.com"),
    new User("", "binh@example.com"),
    new User(null, null)
);

List<String> emails = users.stream()
    .<String>mapMulti((user, emit) -> {
        if (user.email() != null && !user.email().isBlank()) {
            emit.accept(user.email());
        }

        if (user.backupEmail() != null && !user.backupEmail().isBlank()) {
            emit.accept(user.backupEmail());
        }
    })
    .toList();
```

Kết quả gồm ba địa chỉ:

```text
[an@example.com, an.backup@example.com, binh@example.com]
```

Người dùng cuối cùng không tạo kết quả vì cả hai địa chỉ đều không hợp lệ. Người dùng đầu tiên tạo hai kết quả vì mapper gọi `emit.accept` hai lần.

Ví dụ này cũng cho thấy `mapMulti` có thể thực hiện nhiều nhánh phát kết quả trong cùng một mapper. Nếu chỉ cần lọc rồi chuyển đổi đúng một phần tử, tổ hợp `filter` và `map` thường dễ đọc hơn; không cần dùng `mapMulti` chỉ để thay thế các thao tác đơn giản đó.

## 4. Ví dụ: làm phẳng danh sách con

Một trường hợp tự nhiên hơn là mỗi phần tử nguồn chứa một danh sách phần tử con. Ta muốn chuyển danh sách đơn hàng thành danh sách mã sản phẩm của các dòng hàng có số lượng dương.

```java
import java.util.List;

record LineItem(String sku, int quantity) {}
record Order(List<LineItem> items) {}

List<Order> orders = List.of(
    new Order(List.of(
        new LineItem("BOOK-01", 2),
        new LineItem("PEN-02", 0)
    )),
    new Order(List.of(
        new LineItem("BAG-03", 1),
        new LineItem("NOTE-04", 3)
    ))
);

List<String> purchasedSkus = orders.stream()
    .<String>mapMulti((order, emit) -> {
        for (LineItem item : order.items()) {
            if (item.quantity() > 0) {
                emit.accept(item.sku());
            }
        }
    })
    .toList();
```

Kết quả:

```text
[BOOK-01, BAG-03, NOTE-04]
```

Mỗi đơn hàng được xử lý một lần. Trong lần xử lý đó, vòng lặp phát ra mã của từng dòng hàng hợp lệ. Dòng có số lượng bằng không không tạo phần tử đầu ra.

Nếu không cần lọc dòng hàng, mapper có thể ngắn hơn:

```java
List<LineItem> allItems = orders.stream()
    .<LineItem>mapMulti((order, emit) ->
        order.items().forEach(emit)
    )
    .toList();
```

Ở đây, `forEach` gọi Consumer cho từng dòng hàng, vì vậy danh sách các dòng hàng của tất cả đơn được nối thành một Stream duy nhất.

## 5. Ví dụ: tách mỗi dòng văn bản thành nhiều từ

Một dòng văn bản có thể chứa nhiều từ. Ta có thể phát từng từ trực tiếp:

```java
import java.util.List;

List<String> lines = List.of(
    "Java Stream API",
    "mapMulti emits values",
    "Java 16"
);

List<String> words = lines.stream()
    .<String>mapMulti((line, emit) -> {
        for (String word : line.split("\\s+")) {
            if (!word.isBlank()) {
                emit.accept(word);
            }
        }
    })
    .toList();
```

Kết quả:

```text
[Java, Stream, API, mapMulti, emits, values, Java, 16]
```

Mỗi dòng đầu vào tạo ra nhiều từ. Nếu một dòng không có từ hợp lệ, mapper không gọi Consumer và dòng đó đóng góp không phần tử nào.

## 6. Dùng phiên bản chuyên biệt cho kiểu nguyên thủy

Khi kết quả là số, `mapMultiToInt` giúp phát trực tiếp giá trị `int` vào một `IntStream`. Ví dụ tính tổng số lượng của tất cả dòng hàng:

```java
int totalQuantity = orders.stream()
    .mapMultiToInt((order, emit) -> {
        for (LineItem item : order.items()) {
            emit.accept(item.quantity());
        }
    })
    .sum();
```

Mỗi dòng hàng đóng góp một giá trị int. Sau khi các giá trị được phát ra, `sum()` tính tổng trên IntStream.

Tương tự, dùng `mapMultiToLong` khi kết quả là `long`, hoặc `mapMultiToDouble` khi kết quả là `double`. Nên chọn đúng kiểu nguyên thủy của dữ liệu để tránh boxing không cần thiết trong pipeline.

## 7. So sánh mapMulti với map, filter và flatMap

Các thao tác này có mục đích khác nhau:

| Thao tác | Số kết quả từ một phần tử nguồn | Mục đích thường gặp |
|---|---:|---|
| `map` | Chính xác một | Chuyển một giá trị thành một giá trị khác |
| `filter` | Không hoặc một | Giữ hoặc loại phần tử hiện tại |
| `flatMap` | Không, một hoặc nhiều | Chuyển mỗi phần tử thành một Stream rồi làm phẳng |
| `mapMulti` | Không, một hoặc nhiều | Phát trực tiếp các kết quả qua Consumer |

### mapMulti và flatMap

Hai phương thức đều có thể làm phẳng kết quả từ một phần tử nguồn thành nhiều phần tử đầu ra.

Với `flatMap`, mapper phải trả về một Stream cho mỗi phần tử:

```java
List<LineItem> items = orders.stream()
    .flatMap(order -> order.items().stream())
    .toList();
```

Với `mapMulti`, mapper gửi từng phần tử con qua Consumer:

```java
List<LineItem> items = orders.stream()
    .<LineItem>mapMulti((order, emit) ->
        order.items().forEach(emit)
    )
    .toList();
```

Nên cân nhắc `mapMulti` khi logic phát kết quả vốn là một vòng lặp, có nhiều nhánh điều kiện, hoặc mỗi phần tử chỉ tạo ra một số lượng nhỏ kết quả. Phương thức này giúp tránh việc phải viết biểu thức tạo Stream con cho từng phần tử nguồn.

Nên dùng `flatMap` khi phép biến đổi tự nhiên trả về một Stream, khi muốn kết hợp các thao tác Stream trên từng phần tử con, hoặc khi cách viết đó rõ ràng hơn. Cả hai đều là lựa chọn hợp lệ; hãy ưu tiên cách diễn đạt dễ hiểu đối với logic đang xử lý.

### mapMulti có luôn nhanh hơn flatMap không?

Không. API được thiết kế để phù hợp với trường hợp mỗi phần tử tạo ra một số lượng nhỏ kết quả, có thể bằng không. Hiệu năng thực tế còn phụ thuộc vào cách viết mapper, số lượng kết quả, dữ liệu đầu vào, phiên bản JDK và cách pipeline được thực thi. Cài đặt mặc định của API cũng không tạo ra cam kết rằng mọi trường hợp đều tránh được Stream hoặc vùng đệm trung gian.

Vì vậy, hãy chọn `mapMulti` trước hết vì mô hình phát kết quả phù hợp và mã dễ đọc. Nếu hiệu năng là yêu cầu quan trọng, hãy đo trên dữ liệu và môi trường gần với ứng dụng thực tế thay vì mặc định rằng một phương thức luôn nhanh hơn phương thức còn lại.

## 8. Đặc tính khi chạy trong Stream pipeline

`mapMulti` là một intermediate operation (thao tác trung gian). Bản thân lời gọi chưa xử lý toàn bộ dữ liệu ngay lập tức. Mapper được thực thi khi một terminal operation như `toList`, `collect`, `count` hoặc `sum` tiêu thụ pipeline.

Một số hệ quả cần nhớ:

- Nếu pipeline không có terminal operation, mapper chưa được chạy.
- Terminal operation có khả năng dừng sớm có thể chỉ yêu cầu xử lý một phần dữ liệu.
- Với Stream có thứ tự, các giá trị được phát ra theo thứ tự gọi `accept` trong từng lần mapper; thứ tự gặp của các phần tử nguồn được duy trì bởi pipeline có thứ tự.
- `mapMulti` không tự biến Stream thành parallel hoặc sequential. Chế độ xử lý phụ thuộc vào Stream nguồn và các thao tác `parallel()` hoặc `sequential()` trong pipeline.
- Trong parallel Stream, mapper có thể được thực thi đồng thời cho các phần tử nguồn khác nhau. Không nên dùng chung trạng thái có thể thay đổi giữa các lần gọi mapper.

Các hàm hành vi truyền vào Stream nên không can thiệp vào nguồn dữ liệu và nên không phụ thuộc trạng thái thay đổi bên ngoài. Hãy tạo kết quả bằng Consumer thay vì sửa danh sách nguồn hoặc cập nhật một collection dùng chung từ bên trong mapper.

## 9. Lỗi thường gặp và cách tránh

**Không gọi Consumer khi muốn giữ kết quả.** Nếu mapper kết thúc mà không gọi `accept`, phần tử nguồn đó không tạo ra phần tử đầu ra. Hãy kiểm tra các nhánh điều kiện để chắc rằng mọi trường hợp cần giữ đều phát kết quả.

**Gọi Consumer nhiều lần ngoài dự kiến.** Mỗi lần gọi `accept` tạo thêm một phần tử. Nếu vòng lặp chạy qua ba phần tử con thì có thể tạo ba kết quả; hãy kiểm tra điều kiện và số vòng lặp để tránh phát trùng.

**Để trình biên dịch không suy luận được kiểu đầu ra.** Khi kiểu kết quả chưa rõ từ ngữ cảnh, chỉ định kiểu tường minh như `.<String>mapMulti(...)` hoặc khai báo kiểu đích của biến nhận kết quả.

**Giữ Consumer để dùng sau callback.** Consumer đại diện cho điểm phát kết quả trong lần gọi mapper hiện tại. Hãy gọi nó ngay trong callback và không lưu để dùng ở một luồng hoặc tác vụ chạy sau.

**Dùng mapMulti cho một phép biến đổi đơn giản.** Nếu mỗi phần tử luôn tạo đúng một giá trị, dùng `map`. Nếu chỉ cần loại bỏ một số phần tử, dùng `filter`. Chọn thao tác thể hiện đúng ý định sẽ giúp pipeline dễ đọc hơn.

**Giả định mapMulti luôn cải thiện hiệu năng.** Số lượng kết quả lớn, logic mapper phức tạp hoặc đặc điểm dữ liệu có thể làm thay đổi kết quả đo. Hãy benchmark nếu cần tối ưu hiệu năng.

## 10. Lưu ý về kết quả toList()

Các ví dụ dùng `Stream.toList()`, phương thức có từ Java 16. Danh sách trả về không hỗ trợ sửa đổi cấu trúc; các thao tác như `add`, `remove` hoặc `clear` sẽ không được hỗ trợ.

Nếu cần một danh sách có thể thay đổi, hãy thu thập bằng collector tạo danh sách mới:

```java
import java.util.ArrayList;
import java.util.stream.Collectors;

List<String> mutableWords = lines.stream()
    .<String>mapMulti((line, emit) -> {
        for (String word : line.split("\\s+")) {
            if (!word.isBlank()) {
                emit.accept(word);
            }
        }
    })
    .collect(Collectors.toCollection(ArrayList::new));
```

Đây là lựa chọn dựa trên yêu cầu mutability của kết quả; nó không làm thay đổi cách hoạt động của `mapMulti`.

## 11. Khi nào nên chọn mapMulti?

Hãy chọn `mapMulti` khi cần chuyển từng phần tử nguồn thành không, một hoặc một số ít phần tử đầu ra và việc phát kết quả được diễn đạt tự nhiên bằng vòng lặp hoặc các nhánh điều kiện. Các tình huống điển hình gồm:

- Lọc và phát các phần tử con từ một đối tượng cha.
- Tách một bản ghi thành một số giá trị cần xử lý tiếp.
- Phát một hoặc nhiều giá trị tùy điều kiện.
- Chuyển các giá trị sang `IntStream`, `LongStream` hoặc `DoubleStream` bằng các phương thức chuyên biệt.

Nếu mỗi đầu vào luôn tương ứng với một đầu ra, hãy dùng `map`. Nếu chỉ giữ hoặc loại phần tử, hãy dùng `filter`. Nếu phép biến đổi vốn đã tạo ra một Stream và cách viết đó dễ hiểu, `flatMap` vẫn phù hợp.

`mapMulti` bổ sung một cách diễn đạt trực tiếp cho phép biến đổi một-nhiều trong Stream API. Hiểu rõ số lần phát kết quả, phạm vi sử dụng Consumer và đặc tính lazy của pipeline sẽ giúp áp dụng phương thức này chính xác trong các ứng dụng Java hiện đại.

