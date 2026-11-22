# Spliterator: tryAdvance, forEachRemaining và trySplit

## 1. Một bộ duyệt có thể chia phần công việc còn lại

Khi đọc một danh sách, ta có thể muốn lấy từng phần tử một, xử lý nhanh tất cả phần còn lại, hoặc giao một phần chưa xử lý cho một bộ duyệt khác. `Spliterator<T>` cung cấp ba thao tác tương ứng:

| Phương thức | Yêu cầu chính | Giá trị trả về |
| --- | --- | --- |
| `tryAdvance(action)` | Thực hiện hành động trên một phần tử còn lại, nếu có | `boolean` |
| `forEachRemaining(action)` | Thực hiện hành động trên các phần tử còn lại của bộ duyệt này | `void` |
| `trySplit()` | Thử tách một phần chưa duyệt sang một Spliterator khác | Spliterator mới hoặc `null` |

Spliterator là đối tượng dùng để **duyệt và phân chia các phần tử của nguồn**. Nguồn có thể là Collection, mảng hoặc một dạng nguồn khác; bản thân Spliterator không phải danh sách chứa bản sao của mọi dữ liệu. [Java SE 17 — Spliterator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Spliterator.html).

Hình dung một chồng hồ sơ có thứ tự:

~~~text
[A, B, C, D, E, F]
~~~

Một Spliterator đang quản lý việc đọc chồng hồ sơ này. Đọc `A` làm phần chưa đọc còn `B..F`. Sau đó có thể tách một phần của `B..F` cho bộ duyệt khác. Hồ sơ `A` đã xử lý không tự xuất hiện lại trong phần tách.

Trong bài, “còn lại” luôn có nghĩa là phần mà **chính Spliterator đang xét còn chịu trách nhiệm duyệt**, không phải toàn bộ Collection nguồn. Sau khi chia, hai Spliterator có trách nhiệm trên hai phần khác nhau.

Mục tiêu học là theo dõi chính xác trạng thái ấy: phần nào đã đi qua hành động, phần nào được chuyển sang bộ duyệt mới, phần nào vẫn thuộc bộ duyệt cũ, và thời điểm nào thật sự hết phần tử.

## 2. So với Iterator: thay cách yêu cầu phần tử và bổ sung khả năng chia

Một `Iterator` thường được dùng theo cặp `hasNext` và `next`:

~~~java
while (iterator.hasNext()) {
    String value = iterator.next();
    consume(value);
}
~~~

Đây là đoạn minh họa có `iterator` và `consume` do ứng dụng cung cấp. `hasNext` hỏi còn phần tử hay không; `next` trả về phần tử và tiến trạng thái. [Java SE 17 — Iterator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Iterator.html).

Với Spliterator, `tryAdvance` kết hợp việc thử lấy phần tử với việc chuyển nó cho một `Consumer`:

~~~java
boolean moved = spliterator.tryAdvance(value -> consume(value));
~~~

Nếu có phần tử, hành động được gọi với phần tử ấy và phương thức trả `true`. Nếu không có, không có phần tử nào được chuyển cho hành động và phương thức trả `false`.

Spliterator còn có `trySplit` để phân chia phần chưa duyệt. Tuy nhiên, khả năng chia không có nghĩa phải dùng nhiều luồng. Cả ba phương thức đều có thể được dùng trong một chương trình tuần tự để học hoặc để xây dựng thuật toán riêng.

Spliterator cũng không có phương thức `remove` như thao tác tùy chọn của Iterator. Không nên tìm cách dùng `tryAdvance` để thay thế một cơ chế xóa hợp lệ của cấu trúc nguồn.

## 3. tryAdvance: một lời gọi thành công xử lý một phần tử

Chữ ký:

~~~java
boolean tryAdvance(Consumer<? super T> action)
~~~

Với nguồn có thứ tự `A, B, C`, các lời gọi bình thường lần lượt có ý nghĩa:

| Lời gọi | Phần tử chuyển cho action | Kết quả |
| --- | --- | --- |
| Lần 1 | `A` | `true` |
| Lần 2 | `B` | `true` |
| Lần 3 | `C` | `true` |
| Lần 4 | Không có | `false` |

Lần xử lý phần tử cuối vẫn trả `true`. Nó không trả lời câu hỏi “sau lần này còn phần tử tiếp theo không”; nó trả lời câu hỏi “lần gọi này có phần tử để thực hiện hành động không”.

Ví dụ minh họa trong một phương thức:

~~~java
List<String> data = new ArrayList<>(List.of("A", "B", "C"));
Spliterator<String> cursor = data.spliterator();
List<String> visited = new ArrayList<>();

boolean first = cursor.tryAdvance(visited::add);
~~~

Sau lời gọi, `first` bằng `true` và `visited` là `[A]`. Nguồn `data` vẫn là `[A, B, C]`. Trạng thái duyệt đã tiến, chứ phần tử `A` không bị xóa khỏi danh sách.

Các đoạn ngắn trong bài cần import thích hợp; phần chương trình đầy đủ phía sau có toàn bộ import và lệnh chạy.

### 3.1. Boolean không phải kết quả kiểm tra nghiệp vụ

`action` có kiểu `Consumer` và không trả về một quyết định lọc. Nếu hành động tự kiểm tra điều kiện rồi không làm gì thêm, `tryAdvance` vẫn có thể trả `true` vì nó đã lấy một phần tử.

Ví dụ minh họa:

~~~java
boolean moved = cursor.tryAdvance(value -> {
    if (value.startsWith("Z")) {
        System.out.println(value);
    }
});
~~~

Không có dòng nào được in không chứng minh `moved` là `false`. Phần tử đã được lấy có thể chỉ không đạt điều kiện `startsWith`.

Cũng vậy, `visited::add` có thể được thích nghi làm Consumer dù `List.add` vốn có kết quả boolean. Giá trị ấy không trở thành giá trị trả về của `tryAdvance`.

### 3.2. Lấy từng phần tử khi cần kiểm soát nhịp xử lý

`tryAdvance` hữu ích khi bên gọi cần dừng giữa chừng, xử lý một lượng có giới hạn hoặc phối hợp với một điều kiện bên ngoài. Không cần rút hết nguồn trong một lời gọi.

Nếu mục đích duy nhất là xử lý hết phần còn lại, dùng `forEachRemaining` thường diễn tả rõ hơn một vòng lặp gọi `tryAdvance` có thân rỗng.

Sau khi một Spliterator đã hết phần việc, `tryAdvance` với hành động hợp lệ trả `false` và không gọi hành động. Điều này chỉ nói về bộ duyệt đó; một phần đã tách sang Spliterator khác có thể vẫn chưa được đọc.

## 4. forEachRemaining: xử lý phần chưa duyệt, không bắt đầu lại nguồn

Chữ ký:

~~~java
void forEachRemaining(Consumer<? super T> action)
~~~

Nếu đã dùng `tryAdvance` để xử lý `A` và `B` trong nguồn `A..F`, lời gọi `forEachRemaining` tiếp theo chỉ xử lý `C, D, E, F`.

Ví dụ:

~~~java
Spliterator<String> cursor = data.spliterator();
List<String> visited = new ArrayList<>();

cursor.tryAdvance(visited::add);
cursor.tryAdvance(visited::add);
cursor.forEachRemaining(visited::add);
~~~

Với `data` là `[A, B, C, D, E, F]`, `visited` sau cùng cũng là `[A, B, C, D, E, F]`, không phải `[A, B, A, B, C, D, E, F]`.

Phương thức trả `void`, nên không có kết quả boolean báo đã xử lý được bao nhiêu phần tử. Nếu cần kết quả tính toán, hành động hoặc thuật toán bao quanh phải thu kết quả một cách phù hợp.

Theo hợp đồng, `forEachRemaining` thực hiện hành động tuần tự trong luồng hiện tại cho tới khi hết phần tử hoặc hành động ném ngoại lệ. Nếu có đặc tính `ORDERED`, các hành động theo thứ tự gặp của phần nguồn ấy. Cách cài đặt mặc định gọi lặp `tryAdvance`, nhưng một cách cài đặt cụ thể có thể tối ưu vòng duyệt. [Java SE 17 — Spliterator.forEachRemaining](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Spliterator.html#forEachRemaining(java.util.function.Consumer)).

Hai hệ quả thực hành:

- Gọi lại `forEachRemaining` sau khi đã xử lý hết không làm dữ liệu được duyệt lại.
- `forEachRemaining` trên một phần được chia không tự xử lý phần đang thuộc bộ duyệt khác.

Tên phương thức có chữ “all remaining” theo nghĩa mọi phần tử còn lại của **đối tượng nhận lời gọi**, không phải mọi phần tử từng có trong nguồn.

## 5. trySplit: chuyển một phần trách nhiệm duyệt sang bộ duyệt mới

Chữ ký:

~~~java
Spliterator<T> trySplit()
~~~

Nếu chia được, phương thức trả về Spliterator quản lý một phần các phần tử chưa duyệt. Sau lời gọi, phần ấy không còn thuộc phạm vi của Spliterator cũ. Nếu chưa thể hoặc không muốn chia tiếp, nó trả `null`.

Điều cần hình dung là **phân chia**, không phải nhân đôi:

~~~text
trước:
cursor -> [A, B, C, D, E, F]

sau một lần chia trong ví dụ:
prefix -> [A, B, C]
cursor -> [D, E, F]
~~~

Hai phần phải không trùng nhau ở cấp phần tử được nguồn phân chia. Đây không phải yêu cầu rằng các **giá trị** phải khác nhau: nguồn `[X, X, Y]` có hai vị trí chứa `X` và cả hai đều cần được xử lý đúng một lần.

`trySplit` không nhận một Consumer nên không tự thực hiện hành động nghiệp vụ mà ta sẽ truyền cho `tryAdvance` hoặc `forEachRemaining`. Tuy nhiên, không được suy ra nó luôn là thao tác miễn phí, không cấp phát hoặc không đọc gì từ cấu trúc nền. Một cách cài đặt có thể cần chuẩn bị hoặc gom một lô phần tử để tạo phần chia.

### 5.1. Với nguồn ORDERED, phần trả về là tiền tố

Nếu Spliterator báo `ORDERED`, phần trả về phải là một tiền tố thực sự của phần chưa duyệt. Spliterator cũ giữ phần sau. Đây là ràng buộc cho phép thuật toán ghép kết quả đúng thứ tự. [Java SE 17 — Spliterator.trySplit](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Spliterator.html#trySplit()).

Với nguồn có thứ tự `A..F` và một phép chia ba–ba, muốn tái tạo thứ tự nguồn thì duyệt `prefix` trước, rồi `cursor`. Nếu duyệt phần sau trước, mỗi bộ duyệt vẫn có thể tuân thủ thứ tự bên trong phần của nó, nhưng danh sách ghép tổng thể sẽ thành `[D, E, F, A, B, C]`.

Nếu nguồn không có `ORDERED`, không áp đặt lên nó ý nghĩa tiền tố theo một thứ tự nghiệp vụ chưa được bảo đảm. Khả năng chia thành các phần không tự tạo ra thứ tự sắp xếp.

### 5.2. Tỷ lệ chia không bắt buộc luôn là hai nửa

Chia cân bằng thường có lợi cho xử lý song song, nhưng hợp đồng không yêu cầu mọi nguồn chia đúng `50/50`. Cấu trúc cây, nguồn dựa trên bộ duyệt hoặc nguồn khó biết kích thước có thể có chiến lược khác.

Kết quả chính xác `[B, C]` và `[D, E, F]` trong chương trình của bài là quan sát của nguồn `ArrayList` cụ thể sau khi đã đọc `A`. Không lấy những con số đó làm đáp án cố định cho mọi loại Collection.

## 6. Kết hợp cả ba phương thức trên cùng một ví dụ

Nguồn:

~~~text
[A, B, C, D, E, F]
~~~

Đầu tiên:

~~~java
Spliterator<String> cursor = data.spliterator();
List<String> first = new ArrayList<>();
cursor.tryAdvance(first::add);
~~~

Trạng thái lúc này:

~~~text
đã xử lý:   [A]
cursor:     [B, C, D, E, F]
~~~

Tiếp theo:

~~~java
Spliterator<String> prefix = cursor.trySplit();
~~~

Trong ca `ArrayList` được chạy:

~~~text
đã xử lý:   [A]
prefix:     [B, C]
cursor:     [D, E, F]
~~~

Cuối cùng:

~~~java
prefix.forEachRemaining(prefixValues::add);
cursor.forEachRemaining(remainingValues::add);
~~~

Hai danh sách đầu ra là `[B, C]` và `[D, E, F]`. Ghép phần đã xử lý, phần tiền tố và phần còn lại cho `A..F` đúng một lần.

Ba điểm cần kiểm tra:

1. `A` không bị đưa vào phép chia vì nó đã đi qua hành động.
2. Duyệt `cursor` không tự kéo theo `prefix`.
3. Danh sách nguồn không bị xóa hoặc cắt thành hai danh sách mới chỉ vì quyền duyệt đã được chia.

Trong mã tổng quát, phải kiểm tra `prefix != null` trước khi dùng. Chương trình đầy đủ dùng nguồn biết được để minh họa một lần chia thành công và có kiểm tra bảo vệ giả định của ví dụ.

## 7. trySplit trả null không có nghĩa là hết dữ liệu

Một bộ duyệt trên mảng một phần tử có thể không chia thêm được:

~~~java
Spliterator<String> one = Arrays.spliterator(new String[] {"solo"});
Spliterator<String> part = one.trySplit();
~~~

Trong ví dụ này, `part` là `null`. Nhưng `one.tryAdvance(...)` vẫn xử lý được `solo` và trả `true`.

Cần tách hai câu hỏi:

| Câu hỏi | Cách kiểm tra phù hợp |
| --- | --- |
| Có tách thêm được một phần để giao đi không? | Gọi `trySplit` và xem kết quả có null không |
| Lần gọi này có phần tử để xử lý không? | Gọi `tryAdvance` với hành động hợp lệ |
| Muốn xử lý hết phần việc hiện tại | Gọi `forEachRemaining` |

Không nên viết thuật toán chỉ xử lý khi `trySplit` khác `null` rồi bỏ luôn nhánh `null`. Nhánh đó thường chính là phần việc cần được duyệt trực tiếp.

`trySplit` có thể từ chối do nguồn rỗng, ràng buộc cấu trúc, hiệu quả thực hiện hoặc việc đã bắt đầu duyệt khiến cách cài đặt không chia tiếp được. Vì vậy, cả nguồn còn nhiều phần tử cũng không bảo đảm mọi Spliterator luôn chia được.

Với nguồn hữu hạn, việc cố chia lặp đi lặp lại phải đi tới trường hợp không chia tiếp được theo hợp đồng. Tuy nhiên, một thuật toán thực tế vẫn nên có ngưỡng dừng phù hợp, thay vì chia tới đơn vị nhỏ nhất chỉ vì có thể.

## 8. Duyệt đệ quy theo thứ tự: chia được thì chia, không chia được thì xử lý

Đoạn helper sau dùng cho nguồn có thứ tự phù hợp:

~~~java
static <T> void drainInOrder(Spliterator<T> source, List<T> output) {
    Spliterator<T> prefix = source.trySplit();
    if (prefix == null) {
        source.forEachRemaining(output::add);
    } else {
        drainInOrder(prefix, output);
        drainInOrder(source, output);
    }
}
~~~

Đây là phương thức đặt trong một lớp, cần import `Spliterator` và `List`. Chương trình đầy đủ dùng helper với các `ArrayList` nhỏ.

Luồng suy luận:

1. Thử tách phần đầu.
2. Nếu không có phần tách, xử lý trực tiếp phần việc hiện tại.
3. Nếu có, xử lý phần tiền tố trước.
4. Sau đó xử lý phần còn lại của đối tượng cũ.

Việc gọi helper như trên vẫn hoàn toàn tuần tự. Không có dòng mã nào khởi tạo luồng hoặc gửi tác vụ sang bộ thực thi.

Helper phục vụ minh họa nguyên tắc bảo toàn thứ tự. Một hệ thống xử lý dữ liệu lớn cần cân nhắc độ sâu đệ quy, số phần chia, chi phí cấp phát và ngưỡng kích thước. Không nên coi ví dụ chia tới khi `null` là chính sách hiệu năng tối ưu cho mọi nguồn.

Với nguồn không có thứ tự được xác định, tên `drainInOrder` chỉ có thể mang nghĩa thứ tự do thuật toán chọn, không thể cam kết khôi phục một thứ tự ban đầu mà nguồn không hứa cung cấp.

## 9. estimateSize là thông tin hỗ trợ, không thay thế phép thử còn phần tử

`estimateSize()` báo một ước lượng về số phần tử mà bộ duyệt còn có thể đưa ra. Khi không biết, quá đắt để tính hoặc nguồn không hữu hạn, giá trị có thể là `Long.MAX_VALUE`.

`SIZED` và `SUBSIZED` đặt thêm những ràng buộc về kích thước, nhưng có điều kiện liên quan tới việc đã duyệt hoặc chia hay chưa. Không được giả định mọi Spliterator luôn trả số đếm chính xác sau mọi thao tác.

`ArrayList.spliterator()` báo `ORDERED`, `SIZED` và `SUBSIZED`, đồng thời có chính sách liên kết muộn và phát hiện sửa đổi theo khả năng tốt nhất. [Java SE 17 — ArrayList.spliterator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html#spliterator()).

Trong ca thử của bài, sau khi xử lý `A` rồi chia:

~~~text
prefix.estimateSize() = 2
cursor.estimateSize() = 3
~~~

Hai giá trị phù hợp với `[B, C]` và `[D, E, F]` của cách cài đặt được chạy. Đó là thông tin chẩn đoán hữu ích, không phải lý do để thay tất cả vòng duyệt bằng một vòng lặp theo ước lượng.

Tránh mẫu suy luận “estimate lớn hơn không thì chắc chắn còn, estimate bằng không thì chắc chắn hết” khi viết mã nhận một Spliterator bất kỳ mà chưa kiểm tra hợp đồng đặc tính và trạng thái. `tryAdvance` mới trực tiếp thử thực hiện một bước; `forEachRemaining` trực tiếp yêu cầu rút phần còn lại.

Bài chỉ dùng các đặc tính cần thiết để hiểu ba thao tác. Các bit đặc tính là cam kết để thuật toán tận dụng đúng, không phải nhãn tùy ý gắn cho đẹp.

## 10. Chia công việc không tự tạo an toàn đa luồng

Một luồng có thể gọi `trySplit` rồi chuyển Spliterator trả về cho luồng khác. Cách này tạo cơ sở để các phần nguồn được xử lý riêng.

Nhưng không được để hai luồng cùng gọi `tryAdvance` hoặc `trySplit` trên **cùng một đối tượng Spliterator** rồi mặc nhiên coi là an toàn. Hợp đồng Spliterator không yêu cầu đối tượng phải an toàn cho kiểu truy cập đồng thời ấy.

Mô hình trách nhiệm phù hợp là:

~~~text
bộ duyệt ban đầu
      |
      | chia trước khi giao
      +--> phần 1 --> một bên xử lý
      |
      +--> phần 2 --> một bên xử lý khác
~~~

Ngoài quyền sở hữu bộ duyệt, hành động xử lý cũng cần phù hợp. Hai phần nguồn khác nhau cùng gọi `sharedArrayList.add` từ hai luồng vẫn có thể gây lỗi vì nơi thu kết quả bị dùng chung không an toàn.

Nếu cần giữ thứ tự toàn cục, còn phải thiết kế cách ghép kết quả theo thứ tự phần chia. Việc từng phần có `ORDERED` không làm các thời điểm hoàn tất ở nhiều luồng tự sắp hàng đúng thứ tự.

Chương trình của bài cố ý duyệt tất cả trong một luồng, thu vào các danh sách riêng hoặc theo thứ tự đệ quy. Các kết quả được kiểm tra không phải bằng chứng cho một thuật toán đa luồng.

## 11. Hành động null, ngoại lệ và việc sửa nguồn

### 11.1. action null là tham số không hợp lệ

Cả `tryAdvance` lẫn `forEachRemaining` yêu cầu một hành động hợp lệ. Truyền `null` gây `NullPointerException`; không dùng nó như phép hỏi “còn dữ liệu không” mà không muốn xử lý.

Có thể dùng một hành động không làm gì nếu thật sự muốn tiêu thụ một bước mà bỏ giá trị:

~~~java
boolean skipped = cursor.tryAdvance(value -> { });
~~~

Nếu trả `true`, phần tử ấy đã đi qua trạng thái duyệt và không còn nằm trong phần chưa duyệt. Đây là hành động tiêu thụ, không phải thao tác nhìn trước không thay đổi trạng thái.

### 11.2. Ngoại lệ của action được truyền ra ngoài

Nếu hành động ném lỗi ở phần tử `B`, lời gọi đang duyệt dừng và ngoại lệ được truyền cho bên gọi. Tác dụng phụ đã thực hiện trên `A` hoặc trên `B` trước khi ném không tự được hoàn tác.

Hợp đồng còn nêu rằng hành vi tiếp theo của Spliterator không được xác định khi action ném ngoại lệ. Vì thế, không được viết một thuật toán tổng quát dựa vào giả định “bắt lỗi rồi gọi tiếp, chắc chắn sẽ bắt đầu ở phần tử ngay sau B”.

Trong chương trình minh chứng, bộ duyệt đã gặp lỗi được bỏ, không tiếp tục truy vấn hoặc dùng lại nó. Danh sách `seen-before-failure` chỉ cho biết tác dụng phụ quan sát được trước lỗi trong ví dụ ấy.

### 11.3. Nguồn bị sửa trong lúc duyệt không được xử lý bằng phỏng đoán

Với nguồn sửa được, phải biết chính sách liên kết nguồn và sửa đổi đồng thời của Spliterator. `ArrayList` có Spliterator liên kết muộn và fail-fast, nhưng phát hiện sửa đổi chỉ theo khả năng tốt nhất.

Các thay đổi sau khi bộ duyệt đã liên kết với nguồn có thể làm việc duyệt không còn hợp lệ. Việc ghi log bằng `estimateSize` hoặc gọi `trySplit` cũng có thể liên quan đến thời điểm liên kết; không chỉ `tryAdvance` mới đáng chú ý.

Đừng dựa vào `ConcurrentModificationException` để chứng minh không có truy cập sai. `forEachRemaining` có thể tối ưu kiểm tra sửa đổi sau một lô thay vì sau từng phần tử. Giữ nguồn ổn định trong quá trình minh họa và chọn chính sách phối hợp phù hợp nếu ứng dụng cần cập nhật đồng thời.

## 12. Biến thể nguyên thủy và cầu nối sang Stream

### 12.1. Spliterator.OfInt dùng hành động nhận int

Với mảng số nguyên:

~~~java
Spliterator.OfInt numbers = Arrays.spliterator(new int[] {2, 4, 6});
int[] total = {0};

numbers.tryAdvance((int value) -> total[0] += value);
numbers.forEachRemaining((int value) -> total[0] += value);
~~~

Lời gọi đầu tính thêm `2`, lời gọi sau tính thêm `4` và `6`, tổng cuối bằng `12`. Lambda ghi rõ kiểu `int` để chọn dạng hành động nguyên thủy.

Các biến thể `OfInt`, `OfLong` và `OfDouble` có overload dành cho kiểu nguyên thủy. Dùng hành động nguyên thủy phù hợp tránh việc cơ chế duyệt phải đóng gói từng giá trị thành đối tượng chỉ để chuyển cho một Consumer tổng quát.

`total` ở đây là một ô lưu tổng dùng trong ví dụ tuần tự. Không mang nguyên cách cập nhật mảng dùng chung này sang nhiều luồng rồi coi là phép cộng nguyên tử.

### 12.2. Stream có thể tiếp nhận phần việc chưa duyệt

`StreamSupport.stream(spliterator, false)` tạo một Stream tuần tự từ Spliterator đã cho. Nó không yêu cầu quay lại đầu nguồn. [Java SE 17 — StreamSupport.stream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/StreamSupport.html#stream(java.util.Spliterator,boolean)).

Nếu đã dùng `tryAdvance` bỏ qua `A`, Stream nhận bộ duyệt ấy chỉ còn nhìn thấy `B, C, D, E, F`. Tạo một lớp Stream bao ngoài không làm trạng thái duyệt được khởi động lại.

Từ lúc giao bộ duyệt cho pipeline, nên để pipeline quản lý lượt duyệt đó. Không xen các lời gọi thủ công vào cùng Spliterator khi Stream đang sử dụng nó. Nếu cần một lượt mới từ đầu, tạo bộ duyệt mới từ nguồn theo hợp đồng của nguồn.

## 13. Chương trình minh chứng đầy đủ

Lưu mã sau thành **SpliteratorOperationsDemo.java**. Chương trình dùng Java 17+, thư viện chuẩn và không tạo luồng phụ.

`rejects` xác nhận loại ngoại lệ dự kiến. Ca lỗi action chỉ quan sát danh sách đã ghi dấu rồi bỏ bộ duyệt lỗi. Helper đệ quy chỉ dùng cho những nguồn nhỏ, có thứ tự trong ví dụ.

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Spliterator;
import java.util.function.Consumer;
import java.util.stream.StreamSupport;

public class SpliteratorOperationsDemo {
    private static void rejects(
            String label,
            Class<? extends RuntimeException> expected,
            Runnable action) {
        try {
            action.run();
            throw new AssertionError(label + " did not fail");
        } catch (RuntimeException ex) {
            if (!expected.isInstance(ex)) {
                throw ex;
            }
            System.out.println(label + " -> " + ex.getClass().getSimpleName());
        }
    }

    private static <T> void drainInOrder(Spliterator<T> source, List<T> output) {
        Spliterator<T> prefix = source.trySplit();
        if (prefix == null) {
            source.forEachRemaining(output::add);
        } else {
            drainInOrder(prefix, output);
            drainInOrder(source, output);
        }
    }

    public static void main(String[] args) {
        List<String> data = new ArrayList<>(List.of("A", "B", "C", "D", "E", "F"));

        Spliterator<String> cursor = data.spliterator();
        List<String> first = new ArrayList<>();
        System.out.println("advance=" + cursor.tryAdvance(first::add));
        System.out.println("first=" + first);
        Spliterator<String> prefix = cursor.trySplit();
        if (prefix == null) {
            throw new AssertionError("Expected ArrayList split");
        }
        System.out.println("split-size=" + prefix.estimateSize());
        System.out.println("remaining-size=" + cursor.estimateSize());
        List<String> prefixValues = new ArrayList<>();
        List<String> remainingValues = new ArrayList<>();
        prefix.forEachRemaining(prefixValues::add);
        cursor.forEachRemaining(remainingValues::add);
        System.out.println("prefix=" + prefixValues);
        System.out.println("remaining=" + remainingValues);
        System.out.println("source=" + data);
        System.out.println("advance-after-end=" + cursor.tryAdvance(first::add));
        System.out.println("first-still=" + first);

        Spliterator<String> mixed = data.spliterator();
        List<String> visited = new ArrayList<>();
        mixed.tryAdvance(visited::add);
        mixed.tryAdvance(visited::add);
        System.out.println("before-bulk=" + visited);
        mixed.forEachRemaining(visited::add);
        System.out.println("after-bulk=" + visited);
        mixed.forEachRemaining(value -> visited.add("unexpected"));
        System.out.println("after-empty-bulk=" + visited);

        Spliterator<String> singleton = Arrays.spliterator(new String[] {"solo"});
        System.out.println("singleton-split-null=" + (singleton.trySplit() == null));
        List<String> soloValues = new ArrayList<>();
        System.out.println("singleton-advance=" + singleton.tryAdvance(soloValues::add));
        System.out.println("singleton-values=" + soloValues);

        List<String> rebuilt = new ArrayList<>();
        drainInOrder(data.spliterator(), rebuilt);
        System.out.println("recursive=" + rebuilt);
        List<String> duplicateValues = new ArrayList<>();
        drainInOrder(new ArrayList<>(List.of("X", "X", "Y")).spliterator(), duplicateValues);
        System.out.println("duplicates=" + duplicateValues);

        Spliterator<String> empty = List.<String>of().spliterator();
        System.out.println("empty-split-null=" + (empty.trySplit() == null));
        System.out.println("empty-advance=" + empty.tryAdvance(value -> {
            throw new AssertionError("No value expected");
        }));

        rejects("null-advance-action", NullPointerException.class,
                () -> data.spliterator().tryAdvance((Consumer<String>) null));
        rejects("null-bulk-action", NullPointerException.class,
                () -> data.spliterator().forEachRemaining((Consumer<String>) null));

        Spliterator<String> failing = data.spliterator();
        List<String> beforeFailure = new ArrayList<>();
        rejects("action-failure", IllegalArgumentException.class,
                () -> failing.forEachRemaining(value -> {
                    beforeFailure.add(value);
                    if (value.equals("B")) {
                        throw new IllegalArgumentException("stop");
                    }
                }));
        System.out.println("seen-before-failure=" + beforeFailure);

        Spliterator.OfInt primitive = Arrays.spliterator(new int[] {2, 4, 6});
        int[] total = {0};
        primitive.tryAdvance((int value) -> total[0] += value);
        System.out.println("primitive-first-total=" + total[0]);
        primitive.forEachRemaining((int value) -> total[0] += value);
        System.out.println("primitive-full-total=" + total[0]);

        Spliterator<String> forStream = data.spliterator();
        forStream.tryAdvance(value -> { });
        List<String> streamRemainder = StreamSupport.stream(forStream, false).toList();
        System.out.println("stream-remainder=" + streamRemainder);
    }
}
~~~

Biên dịch và chạy tại thư mục chứa tệp:

~~~shell
javac --release 17 -encoding UTF-8 SpliteratorOperationsDemo.java
java SpliteratorOperationsDemo
~~~

Stdout chính xác:

~~~text
advance=true
first=[A]
split-size=2
remaining-size=3
prefix=[B, C]
remaining=[D, E, F]
source=[A, B, C, D, E, F]
advance-after-end=false
first-still=[A]
before-bulk=[A, B]
after-bulk=[A, B, C, D, E, F]
after-empty-bulk=[A, B, C, D, E, F]
singleton-split-null=true
singleton-advance=true
singleton-values=[solo]
recursive=[A, B, C, D, E, F]
duplicates=[X, X, Y]
empty-split-null=true
empty-advance=false
null-advance-action -> NullPointerException
null-bulk-action -> NullPointerException
action-failure -> IllegalArgumentException
seen-before-failure=[A, B]
primitive-first-total=2
primitive-full-total=12
stream-remainder=[B, C, D, E, F]
~~~

Mã đã biên dịch với `--release 17` và chạy trên JDK 24.0.2. Cờ biên dịch kiểm tra mức ngôn ngữ/API Java 17; kết quả chạy được xác nhận trên JVM đã nêu, không phải một lần chạy JVM 17.

Đọc kết quả:

- `advance` và `first` cho biết một bước đã xử lý `A`.
- `split-size`, `prefix` và `remaining` thể hiện lần chia phần `B..F` của ArrayList được dùng.
- `source` không đổi vì duyệt không xóa hay cắt Collection nguồn.
- `advance-after-end` trả false mà `first-still` không có phần tử mới.
- Nhóm `before-bulk` và `after-bulk` cho thấy forEachRemaining tiếp tục trạng thái đã có.
- `singleton-split-null` cùng `singleton-advance` chứng minh không chia được chưa có nghĩa hết phần tử.
- `recursive` giữ thứ tự, còn `duplicates` giữ cả hai vị trí có giá trị `X`.
- Nhóm `empty` không gọi action trên một phần tử không tồn tại.
- Các ca `null` kiểm tra tham số action; `action-failure` kiểm tra ngoại lệ từ chính hành động.
- Nhóm `primitive` minh họa overload nhận int.
- `stream-remainder` xác nhận Stream chỉ nhận phần chưa duyệt của Spliterator.

## 14. Thực hành có đáp án

### Bài 1 — Ý nghĩa true ở phần tử cuối

Một Spliterator còn đúng một phần tử. Lời gọi `tryAdvance(action)` thành công trả gì? Lời gọi tiếp theo với action hợp lệ trả gì?

**Đáp án:** Lần xử lý phần tử cuối trả `true` vì có một phần tử được chuyển cho action. Lần sau trả `false` vì khi bắt đầu lời gọi đã không còn phần tử. Boolean không phải lời hứa rằng sau lần xử lý còn một phần tử tiếp nữa.

### Bài 2 — forEachRemaining bắt đầu ở đâu?

Nguồn `A, B, C, D` đã được `tryAdvance` xử lý hai lần. Gọi `forEachRemaining` sẽ xử lý phần nào? Có xóa dữ liệu nguồn không?

**Đáp án:** Xử lý `C` và `D`, theo thứ tự nếu nguồn có ORDERED. `A` và `B` không xuất hiện lại. Bản thân việc tiến trạng thái duyệt không xóa các phần tử khỏi Collection nguồn.

### Bài 3 — null từ trySplit

Một bộ duyệt trả `null` khi gọi `trySplit`. Có được kết luận tất cả phần tử đã được xử lý không?

**Đáp án:** Không. `null` chỉ cho biết lời gọi không tách được phần mới. Có thể nguồn còn một phần tử, không hỗ trợ chia hoặc từ chối vì lý do hiệu quả. Tiếp tục xử lý phần hiện tại bằng thao tác duyệt phù hợp.

### Bài 4 — Tránh mất phần việc sau chia

Với nguồn ORDERED còn `A, B, C, D`, phép chia trả một prefix `A, B` và bộ duyệt cũ giữ `C, D`. Nếu chỉ duyệt bộ cũ thì thiếu gì? Muốn ghép đúng thứ tự phải làm sao?

**Đáp án:** Thiếu phần `A, B` đang thuộc prefix. Duyệt và thu kết quả cả hai phần; khi cần thứ tự nguồn, ghép kết quả prefix trước phần cũ. Bộ cũ không còn tự bao gồm phần đã giao đi.

### Bài 5 — Hai giá trị bằng nhau có phải trùng công việc không?

Nguồn là `[X, X, Y]`. Sau chia rồi duyệt, kết quả vẫn chứa hai `X`. Có phải trySplit đã nhân đôi dữ liệu không?

**Đáp án:** Không. Hai vị trí khác nhau có thể chứa giá trị bằng nhau. Phân chia phải bảo toàn các phần tử nguồn theo phạm vi, không tự loại các giá trị trùng. Cần đối chiếu số lần xuất hiện ban đầu thay vì suy ra từ `equals` của các giá trị.

### Bài 6 — Action ném lỗi rồi gọi tiếp

`forEachRemaining` đã chạy action trên `A`, đến `B` thì action ném lỗi. Có thể viết mã tổng quát bắt lỗi rồi tiếp tục bộ duyệt với giả định sẽ bắt đầu ở `C` không?

**Đáp án:** Không. Hành vi tiếp theo của Spliterator sau ngoại lệ từ action không được xác định theo hợp đồng chung. Các tác dụng phụ trước lỗi cũng không tự quay lui. Thiết kế một chiến lược xử lý lỗi riêng hoặc tạo lại lượt xử lý phù hợp thay vì giả định vị trí tiếp tục.

### Bài 7 — Chia rồi dùng nhiều luồng

Sau `trySplit`, có thể cho hai luồng cùng thao tác trên một trong hai đối tượng Spliterator để “tăng tốc thêm” không? Dùng chung một ArrayList đầu ra có tự an toàn không?

**Đáp án:** Không có bảo đảm an toàn khi nhiều luồng cùng thao tác trên cùng Spliterator. Cần giao quyền xử lý từng bộ duyệt cho một bên tại một thời điểm. Nơi thu kết quả cũng phải có thiết kế phù hợp; phân chia nguồn không làm ArrayList dùng chung trở nên an toàn.

### Bài 8 — Bọc Stream có làm quay lại đầu không?

Một Spliterator của `[A, B, C]` đã xử lý `A`. Sau đó tạo `StreamSupport.stream(s, false)` và thu danh sách. Stream có lấy lại `A` không?

**Đáp án:** Không, nó nhận trạng thái phần chưa duyệt của `s` và chỉ có `B, C` trong ví dụ này. Muốn đọc lại từ đầu phải có bộ duyệt mới từ nguồn còn phù hợp, không phải chỉ tạo lớp Stream bao ngoài bộ duyệt đã tiến.

## 15. Cách theo dõi đúng ba thao tác

Trước mỗi lời gọi, xác định phần việc đang thuộc Spliterator nào. `tryAdvance` chuyển một phần tử qua hành động; `forEachRemaining` rút phần việc còn lại của bộ duyệt đó; `trySplit` chuyển một phần trách nhiệm chưa duyệt sang bộ duyệt khác hoặc báo chưa chia được.

Khi cần thứ tự, xem nguồn có ORDERED và giữ quy tắc tiền tố trước phần sau. Khi cần nhiều luồng, tách quyền sở hữu bộ duyệt và thiết kế cả nơi nhận kết quả. Khi gặp lỗi action hoặc nguồn bị sửa, quay lại hợp đồng nguồn thay vì đoán vị trí con trỏ.

Giữ mô hình phần đã xử lý, phần được giao đi và phần còn lại sẽ giúp dùng Spliterator đúng mà không nhầm phép chia với sao chép dữ liệu, không bỏ nhánh trySplit trả null và không vô tình đọc lại hoặc bỏ sót công việc.
