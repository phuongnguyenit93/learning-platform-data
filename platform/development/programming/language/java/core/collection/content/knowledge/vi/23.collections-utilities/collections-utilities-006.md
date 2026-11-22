# Collections.copy: kích thước đích và khác biệt với tạo bản sao mới

Tên `copy` dễ khiến người đọc nghĩ rằng lời gọi sẽ tạo một list mới chứa dữ liệu nguồn. `Collections.copy` làm một việc cụ thể hơn: nó **ghi các phần tử nguồn vào những vị trí đã có của list đích**, bắt đầu từ vị trí 0.

Điểm cần nhớ là `destination.size() >= source.size()`, không phải capacity của đích đủ lớn. Đích cũng phải hỗ trợ thay phần tử. Khi đích dài hơn nguồn, phần đuôi đích được giữ nguyên; phương thức không thu nhỏ hay nối thêm list.

Bài này giải thích hợp đồng ấy bằng Java 17 và đối chiếu nó với `new ArrayList<>(source)`, `addAll` và `List.copyOf`. Các ví dụ cũng tách việc sao chép vật chứa khỏi việc nhân bản đối tượng phần tử.

## 1. Đọc chữ ký theo đúng hướng dữ liệu

Chữ ký của phương thức:

~~~java
public static <T> void copy(
        List<? super T> dest,
        List<? extends T> src
)
~~~

Đây là phần khai báo API, không phải một phương thức cần tự cài lại. **Đích đứng trước, nguồn đứng sau**:

~~~java
Collections.copy(destination, source);
~~~

Phương thức trả `void`. Không có list kết quả mới để gán từ lời gọi. Đối tượng list đích đã tồn tại từ trước và chính nó bị thay dữ liệu.

Nguồn cần đọc được các phần tử; nó có thể là list không sửa được. Đích cần đủ số vị trí đang có và cần cho thay phần tử ở các vị trí được ghi. Hai yêu cầu “đủ vị trí” và “được quyền thay” độc lập nhau.

Về kiểu dữ liệu, nguồn sản xuất phần tử nên có `? extends T`; đích tiêu thụ phần tử nên có `? super T`. Nhờ vậy có thể đưa dữ liệu `Integer` vào một `List<Number>` hợp lệ mà không ép kiểu raw.

~~~java
List<Integer> source = List.of(7, 8);
List<Number> destination =
        new ArrayList<>(List.<Number>of(0.5, 1.5, 2.5));

Collections.copy(destination, source);
~~~

Đoạn trên là mã minh họa trong một phương thức có đủ import. Đích thành `[7, 8, 2.5]`. Kiểu rộng hơn của đích nhận được các số nguyên; vị trí còn lại vẫn giữ số thực cũ.

## 2. Hậu điều kiện: ghi đè đoạn đầu và giữ phần còn lại

Giả sử hai list độc lập ban đầu có nội dung:

~~~text
source:      [A, B]
destination: [old0, old1, tail2, tail3]
~~~

Sau `Collections.copy(destination, source)`:

~~~text
source:      [A, B]
destination: [A, B, tail2, tail3]
~~~

Với nguồn có `n` phần tử và đích có `m` phần tử, khi phép copy hợp lệ hoàn thành trên hai vùng không ảnh hưởng lẫn nhau:

- Các vị trí `0` đến `n - 1` của đích nhận phần tử tương ứng từ nguồn.
- Các vị trí `n` đến `m - 1` của đích giữ nguyên.
- Kích thước đích vẫn là `m`.
- Không có bước `add` để nới đích hoặc `remove` để làm ngắn đích.

Đó là hợp đồng của [Collections.copy, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#copy(java.util.List,java.util.List)).

### Copy nguồn ngắn hơn không xóa dữ liệu cũ ở đuôi

Nếu tiếp tục copy `[Z]` vào đích đang là `[A, B, tail2, tail3]`, đích thành:

~~~text
[Z, B, tail2, tail3]
~~~

B, tail2 và tail3 vẫn còn. Nếu yêu cầu của ứng dụng là “đích có đúng nội dung và đúng số phần tử như nguồn”, cần xử lý việc thay toàn bộ dữ liệu bằng một chiến lược khác. `copy` riêng nó chỉ thay đoạn đầu.

Điều này quan trọng khi tái sử dụng một list làm vùng kết quả: dữ liệu cũ ở đuôi không tự biến thành dữ liệu không còn hiệu lực. API của ứng dụng phải nói rõ độ dài dữ liệu hợp lệ hoặc quản lý kích thước list đúng yêu cầu.

### Giữ đối tượng đích đồng nghĩa các tham chiếu khác thấy thay đổi

~~~java
List<String> alias = destination;
Collections.copy(destination, source);
~~~

`alias` và `destination` vẫn trỏ tới cùng một list. Người giữ `alias` nhìn thấy dữ liệu ở các vị trí được thay.

Không giống việc tạo một list mới rồi gán lại riêng biến cục bộ, cách copy vào đối tượng hiện có giữ nguyên định danh của vật chứa. Điều đó hữu ích khi một thành phần cố ý sở hữu các ô dữ liệu sẵn có, nhưng cũng có thể gây tác động ngoài ý muốn nếu đích đang được chia sẻ.

## 3. Size là số phần tử thật; capacity chỉ là sức chứa

### Lỗi thường gặp với hàm tạo nhận số nguyên

~~~java
List<String> source = List.of("A", "B");
List<String> destination = new ArrayList<>(source.size());

Collections.copy(destination, source);
~~~

Đây là ví dụ cố ý sai: đích có capacity ban đầu cho 2 phần tử nhưng `size()` vẫn bằng 0. Chưa có vị trí 0 hay 1 để thay, nên copy nguồn không rỗng ném `IndexOutOfBoundsException`.

`new ArrayList<>(n)` tạo list rỗng với sức chứa ban đầu, không tạo `n` phần tử `null`. `ensureCapacity(n)` cũng không bổ sung phần tử vào list. [Hàm tạo ArrayList(int), Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html#%3Cinit%3E(int)).

Chỉ số hợp lệ được xác định bởi `size`, không phải lượng bộ nhớ phía trong đã được dự trữ. Sau khi `clear` một list, `size` về 0 dù cách quản lý bộ nhớ bên trong có thể vẫn còn vùng đã cấp phát; list ấy cũng chưa có các ô để `set` hoặc copy vào.

### Cần các phần tử ban đầu nếu muốn copy vào list mới

Một cách tạo đủ vị trí là:

~~~java
List<String> destination =
        new ArrayList<>(Collections.nCopies(source.size(), "?"));

Collections.copy(destination, source);
~~~

Lúc này hàm tạo `ArrayList(Collection)` nhận một collection có đúng số phần tử, nên list mới có các vị trí tương ứng. Nó cho thay phần tử, vì thế đáp ứng cả hai yêu cầu.

Có thể dùng một vòng lặp `add` để tạo đủ các ô ban đầu. Không bắt buộc dùng `nCopies`; điều quyết định là list đích thật sự đã có số phần tử cần thay.

Tuy nhiên, nếu mục tiêu duy nhất là một list mới giống nguồn, tạo ô rồi copy thường vòng vèo hơn cần thiết:

~~~java
List<String> result = new ArrayList<>(source);
~~~

Cách này vừa tạo vật chứa mới vừa đưa các phần tử nguồn vào ngay từ hàm tạo. Nó không cần một đối tượng đích đang có để ghi đè.

### Ba trạng thái có vẻ gần nhau nhưng khác điều kiện

| Cách chuẩn bị đích | Size với `n > 0` | Có thay phần tử được không? | Đủ làm đích copy n phần tử? |
| --- | --- | --- | --- |
| `new ArrayList<T>(n)` | 0 | Có thể thay khi vị trí đã tồn tại, nhưng hiện chưa có | Không |
| `Collections.nCopies(n, value)` | n | Không hỗ trợ thay | Không |
| `new ArrayList<>(Collections.nCopies(n, value))` | n | Có | Có |
| `new ArrayList<>(source)` | Size của nguồn | Có | Có, nhưng thường đã đạt mục tiêu tạo bản sao mới |

Không lấy việc list hỗ trợ `add` để thay điều kiện size. Một `ArrayList` rỗng có thể thêm nhưng không cho `set(0, value)` vì vị trí 0 chưa tồn tại.

## 4. Đích đủ dài chưa chắc cho thay phần tử

### Quyền `set` khác với quyền tăng giảm kích thước

`copy` cần thay giá trị ở các ô. Nó không đòi đích phải là một `ArrayList` và không bắt buộc list đổi kích thước được.

Ví dụ:

~~~java
String[] array = {"x", "y", "keep"};
List<String> destination = Arrays.asList(array);

Collections.copy(destination, List.of("A", "B"));
~~~

List từ `Arrays.asList` có kích thước cố định nhưng cho thay phần tử, nên copy thành công. Chính mảng thành `[A, B, keep]` vì list là view dựa trên mảng. [API Arrays.asList, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html#asList(T...)).

Đây là tình huống mà “không `add` được” không ngăn việc dùng làm đích copy.

### List không sửa được không cấp quyền ghi đè

Một list do `List.of`, `List.copyOf` hoặc `Collections.nCopies` tạo có thể có đủ số phần tử nhưng không hỗ trợ thay. Copy dữ liệu thực sự vào nó sẽ ném `UnsupportedOperationException`.

~~~java
List<String> destination = List.of("?", "?");
Collections.copy(destination, List.of("A", "B"));
~~~

Đoạn trên cố ý minh họa lỗi quyền sửa. Việc `destination` có kiểu `List<String>` không đồng nghĩa mọi phương thức sửa khai báo trên giao diện đều được hỗ trợ.

`List.set` là thao tác tùy chọn. Ngoài quyền sửa, list cụ thể còn có thể áp ràng buộc về loại phần tử hoặc `null`. [Hợp đồng List.set, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#set(int,E)).

### Nguồn không cần quyền sửa

Nguồn chỉ được đọc để lấy phần tử. `List.of("A", "B")` làm nguồn hợp lệ dù nó không cho `set`.

Đừng đổi nhầm hai tham số rồi cho rằng lỗi phát sinh ở nguồn. Đích là tham số thứ nhất, và quyền thay phần tử của nó mới là điều cần cho quá trình ghi.

Cũng không dùng source rỗng làm cách kiểm tra tổng quát quyền sửa đích. Khi không có phần tử nào để thay, có thể không có thao tác ghi nào được thực hiện; một lần không ném lỗi không chứng minh đích dùng được cho nguồn không rỗng.

## 5. So sánh copy vào đối tượng cũ với tạo kết quả mới

| Thao tác | Có vật chứa kết quả mới? | Tác động lên đích hiện có | Size sau thao tác | Quyền sửa kết quả |
| --- | --- | --- | --- | --- |
| `Collections.copy(dest, src)` | Không tự tạo | Ghi đè đoạn đầu | Giữ size cũ của dest | Theo loại dest đã chọn |
| `new ArrayList<>(src)` | Có, một ArrayList mới | Không cần dest cũ | Bằng số phần tử nguồn | Sửa được |
| `dest.addAll(src)` | Không tự tạo | Chèn/nối phần tử vào dest | Tăng theo số phần tử thêm | Dest phải hỗ trợ thêm |
| `List.copyOf(src)` | Trả list có hợp đồng không sửa được; có thể tái sử dụng kết quả thích hợp | Không ghi đè dest cũ | Bằng số phần tử nguồn | Không sửa được; từ chối phần tử null |

### Khi cần giữ nguyên đối tượng đích và các ô phía sau

`Collections.copy` phù hợp khi đã có vùng list đủ lớn và chủ đích là thay một đoạn đầu. Ví dụ một bộ hiển thị đang sở hữu những ô vị trí cố định, cần cập nhật các vị trí đầu và giữ phần khác theo quy tắc riêng.

Phải biết ai đang giữ tham chiếu tới đích. Copy làm họ nhìn thấy thay đổi. Nếu mục tiêu là trả một giá trị riêng cho người gọi, việc giữ một đích dùng chung có thể đi ngược yêu cầu.

### Khi cần bản làm việc chỉnh sửa độc lập về cấu trúc

`new ArrayList<>(source)` là lựa chọn trực tiếp. Các lần thêm/xóa/thay tham chiếu trên list mới không điều khiển các ô của list nguồn.

Nó vẫn giữ các tham chiếu tới phần tử. Độc lập về cấu trúc list chưa là độc lập về mọi đối tượng bên trong. [Hàm tạo ArrayList(Collection), Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html#%3Cinit%3E(java.util.Collection)).

### Khi cần nối dữ liệu

`addAll` giữ phần tử cũ và thêm phần tử nguồn vào cuối nếu dùng dạng không chỉ số. Đích `[old, tail]` thêm `[A, B]` thành `[old, tail, A, B]`.

Điều này khác copy, vì copy cùng nguồn lên đích ấy thành `[A, B]` và không làm size tăng. Không thay thế một lời gọi bằng lời gọi kia chỉ vì cả hai đều đưa dữ liệu từ nguồn sang đích.

### Khi cần một list không sửa được từ nguồn

`List.copyOf` trả kết quả không theo những thay đổi thành phần sau đó của collection nguồn, nhưng không nhân bản sâu các đối tượng phần tử. Nó từ chối `null` trong nguồn và không bảo đảm mỗi lần gọi tạo một định danh list mới.

Tên `copyOf` vì thế cũng không cho phép suy “luôn cấp phát một object mới hoàn toàn”. Dùng hợp đồng nội dung và quyền sửa, không dùng `==` để xác minh một bản dữ liệu thích hợp. [API List.copyOf, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)).

## 6. Sao chép phần tử ở đây là sao chép giá trị tham chiếu

Giả sử nguồn chứa một đối tượng `Box` có số lượng sửa được:

~~~text
source[0] ───────> Box("stock", 1)
~~~

Sau copy vào đích, quan hệ là:

~~~text
source[0] ───────┐
                ├──> cùng một Box("stock", 1)
destination[0] ─┘
~~~

Không có bước gọi hàm tạo `Box` mới. Nếu đổi `count` của đối tượng đó thành 2, cả nguồn và đích đều đọc thấy `stock:2`.

Ngược lại, `destination.set(0, new Box("local", 9))` thay tham chiếu riêng ở ô đích. Ô nguồn vẫn trỏ tới đối tượng `stock`. Hai loại thao tác phải được phân biệt:

1. **Sửa đối tượng đang được chia sẻ:** có thể hiện qua cả hai list.
2. **Thay tham chiếu tại một vị trí của list đích:** không tự thay tham chiếu tương ứng của nguồn độc lập.

Tạo `new ArrayList<>(source)` cũng sao chép phần tử theo cách này. `List.copyOf(source)` không đóng băng các đối tượng bên trong chỉ vì list ngoài không sửa được.

Nếu yêu cầu là người nhận được chỉnh sửa hoàn toàn riêng, phải quyết định cách sao chép từng phần sửa được của mô hình. Nếu yêu cầu là dữ liệu không thay đổi sau công bố, cần một biểu diễn được bảo vệ đầy đủ. Hai mục tiêu ấy không tự được giải quyết bởi tên “copy”.

Tài liệu `Collection` phân biệt rõ tính không sửa được của vật chứa với trạng thái phần tử. [Collection, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html#unmodcoll).

## 7. Copy vào một đoạn và xử lý hai vùng chồng lấp

### Dùng `subList` làm đích có độ lệch

`Collections.copy` không có tham số chỉ số bắt đầu. Có thể truyền view của đoạn cần ghi:

~~~java
List<String> destination =
        new ArrayList<>(List.of("L", "x", "y", "R"));
List<String> source = List.of("A", "B");

Collections.copy(destination.subList(1, 3), source);
~~~

View có hai phần tử tương ứng vị trí 1 và 2 của nguồn đích. Kết quả list gốc là `[L, A, B, R]`. Vị trí 0 của view không phải vị trí 0 của list gốc.

Cận cuối của `subList(from, to)` không được lấy. Đoạn `[1, 3)` có độ dài 2. Vẫn phải bảo đảm view có đủ size cho nguồn và hỗ trợ thay phần tử.

`subList` không tự tạo một bản sao. Các lần ghi vào view tác động lên list nền. Không thêm/xóa cấu trúc list nền qua đường khác rồi tiếp tục dùng view như thể vòng đời của nó không đổi. [API List.subList, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#subList(int,int)).

### Nguồn và đích có thể cùng chia sẻ list nền

Nếu lấy hai đoạn của cùng list, một lần ghi đích có thể thay dữ liệu mà nguồn còn định đọc ở bước sau. Không nên suy rằng `Collections.copy` luôn chụp toàn bộ nguồn trước khi ghi hoặc tự xử lý mọi tình huống chồng lấp như một API sao chép mảng có hợp đồng riêng.

Nếu ý định là chuyển dữ liệu **ban đầu** của một đoạn sang đoạn chồng lấp, tạo bản chụp nguồn tách biệt trước:

~~~java
List<String> values =
        new ArrayList<>(List.of("A", "B", "C", "D", "E"));

List<String> snapshot =
        new ArrayList<>(values.subList(0, 3));

Collections.copy(values.subList(1, 4), snapshot);
~~~

Nguồn đã chốt ở tầng list là `[A, B, C]`. Ghi vào các vị trí 1, 2, 3 cho kết quả `[A, A, B, C, E]`.

Ví dụ không dự đoán kết quả của một cách gọi chồng lấp không có bản chụp. Nó thiết kế nguồn và đích để dữ liệu cần đọc không còn bị chính quá trình ghi làm đổi.

Nếu phần tử là đối tượng sửa được và bạn cần cả trạng thái của chúng tại một thời điểm, một bản sao list vẫn chưa đủ để chụp sâu. Trong ví dụ các phần tử là chuỗi nên vấn đề đang xét là các vị trí của list.

## 8. `null`, lỗi và giới hạn của một lần copy

### Chính list không được là `null`

Truyền nguồn hoặc đích là `null` gây `NullPointerException`. Một nguồn `null` không có cùng nghĩa với list nguồn rỗng.

Nguồn rỗng có size 0 nên không có phần tử nào cần chuyển. Đích sửa được chứa `[keep]` vẫn giữ `[keep]` trong thí nghiệm. Đừng dùng một nguồn rỗng để thay thao tác làm rỗng đích.

### Phần tử `null` phụ thuộc hợp đồng đích

Với nguồn `[null, N]` và đích `ArrayList` có ba ô `[?, ?, tail]`, copy cho `[null, N, tail]`. `ArrayList` cho phép `null`.

Một list cụ thể có thể từ chối `null` hoặc một số loại giá trị. Đủ size và có phương thức `set` vẫn chưa bảo đảm mọi dữ liệu bất kỳ là hợp lệ với đích.

Trong khi đó, `List.copyOf(source)` từ chối nguồn có phần tử `null`. Đây là khác biệt hành vi phải xét khi đổi cách tạo dữ liệu.

### Không coi lỗi là một lời hứa rollback

Các lỗi điển hình gồm đích quá ngắn và không hỗ trợ thay phần tử. Với list tùy chỉnh hoặc dữ liệu không hợp lệ với đích, còn có thể có lỗi trong khi đọc/ghi các phần tử.

Hợp đồng không cung cấp một giao dịch với bảo đảm tự phục hồi toàn bộ dữ liệu cũ nếu mọi bước không hoàn thành. Không dựa vào một thí nghiệm lỗi kích thước để suy ra mọi lỗi ở mọi loại list đều xảy ra trước lần ghi đầu tiên.

Nếu cần kiểm tra/biến đổi dữ liệu có thể thất bại, chuẩn bị và kiểm tra trên dữ liệu riêng trước khi công bố thay đổi theo giao thức sở hữu của ứng dụng. Điều đó vẫn khác với bảo đảm cập nhật nguyên tử cho một list đang được chia sẻ.

### Không có ảnh chụp đồng thời tự động

Nếu nguồn thay đổi trong khi copy, hoặc luồng khác đọc đích giữa các bước ghi, kết quả có thể không là một trạng thái thống nhất theo yêu cầu nghiệp vụ.

Cần giữ nguồn ổn định và kiểm soát quyền ghi/đọc đích trong toàn khoảng thao tác nếu yêu cầu có tính nhất quán. Đồng bộ từng lời gọi nhỏ không tự gộp cả quá trình copy thành một giao dịch ứng dụng.

## 9. Chương trình hoàn chỉnh và bằng chứng chạy

Lưu mã vào **`ListCopyDemo.java`**. Hàm `rejects` kiểm tra đúng loại ngoại lệ mong đợi; nếu thao tác thành công ngoài dự kiến hoặc ném sai loại, chương trình dừng bằng `AssertionError`.

Các nguồn `String` đơn giản dùng để kiểm tra size và đoạn đuôi. Đối tượng `Box` được dùng riêng để nhìn thấy sự chia sẻ phần tử; không có cách tạo list nào trong nhóm thí nghiệm tự nhân bản `Box`.

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.LinkedList;
import java.util.List;

public class ListCopyDemo {
    static final class Box {
        private final String name;
        private int count;

        Box(String name, int count) {
            this.name = name;
            this.count = count;
        }

        @Override
        public String toString() {
            return name + ":" + count;
        }
    }

    private static void rejects(
            String label,
            Class<? extends RuntimeException> expected,
            Runnable action) {
        try {
            action.run();
            throw new AssertionError(label + " unexpectedly succeeded");
        } catch (RuntimeException ex) {
            if (!expected.isInstance(ex)) {
                throw new AssertionError(label + " wrong exception", ex);
            }
            System.out.println(label + "=" + ex.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        List<String> source = List.of("A", "B");
        List<String> destination = new ArrayList<>(
                List.of("old0", "old1", "tail2", "tail3"));
        List<String> alias = destination;
        Collections.copy(destination, source);
        System.out.println("prefix.destination=" + destination);
        System.out.println("prefix.size=" + destination.size());
        System.out.println("prefix.sameObject=" + (alias == destination));
        Collections.copy(destination, List.of("Z"));
        System.out.println("prefix.afterShortSource=" + alias);
        System.out.println("source.after=" + source);

        List<String> capacityOnly = new ArrayList<>(source.size());
        System.out.println("capacity.size=" + capacityOnly.size());
        rejects("capacity.copy", IndexOutOfBoundsException.class,
                () -> Collections.copy(capacityOnly, source));
        List<String> tooSmall = new ArrayList<>(List.of("old"));
        rejects("tooSmall.copy", IndexOutOfBoundsException.class,
                () -> Collections.copy(tooSmall, source));

        List<String> readyTarget =
                new ArrayList<>(Collections.nCopies(source.size(), "?"));
        Collections.copy(readyTarget, source);
        System.out.println("readyTarget=" + readyTarget);
        rejects("readonly.copy", UnsupportedOperationException.class,
                () -> Collections.copy(List.of("?", "?"), source));
        rejects("nCopies.copy", UnsupportedOperationException.class,
                () -> Collections.copy(Collections.nCopies(2, "?"), source));

        String[] backing = {"x", "y", "keep"};
        Collections.copy(Arrays.asList(backing), source);
        System.out.println("fixed.array=" + Arrays.toString(backing));

        List<String> fresh = new ArrayList<>(source);
        fresh.add("C");
        System.out.println("fresh.editable=" + fresh);
        List<String> appended = new ArrayList<>(List.of("old", "tail"));
        appended.addAll(source);
        System.out.println("append.result=" + appended);

        List<Number> numbers =
                new ArrayList<>(List.<Number>of(0.5, 1.5, 2.5));
        Collections.copy(numbers, List.of(7, 8));
        System.out.println("numbers.destination=" + numbers);

        List<Box> boxSource =
                new ArrayList<>(List.of(new Box("stock", 1)));
        List<Box> boxDestination =
                new ArrayList<>(Collections.<Box>nCopies(1, null));
        Collections.copy(boxDestination, boxSource);
        List<Box> freshBoxes = new ArrayList<>(boxSource);
        List<Box> readonlyBoxes = List.copyOf(boxSource);
        System.out.println("boxes.sameElement="
                + (boxSource.get(0) == boxDestination.get(0)));
        boxSource.get(0).count = 2;
        System.out.println("boxes.source=" + boxSource);
        System.out.println("boxes.destination=" + boxDestination);
        System.out.println("boxes.fresh=" + freshBoxes);
        System.out.println("boxes.readonly=" + readonlyBoxes);
        boxDestination.set(0, new Box("local", 9));
        System.out.println("boxes.afterDestinationReplace=" + boxDestination);
        System.out.println("boxes.sourceAfterReplace=" + boxSource);

        List<String> withNull = Arrays.asList(null, "N");
        List<String> nullableDestination =
                new ArrayList<>(List.of("?", "?", "tail"));
        Collections.copy(nullableDestination, withNull);
        System.out.println("nullable.destination=" + nullableDestination);
        rejects("nullable.copyOf", NullPointerException.class,
                () -> List.copyOf(withNull));

        List<String> window =
                new ArrayList<>(List.of("L", "x", "y", "R"));
        Collections.copy(window.subList(1, 3), source);
        System.out.println("window.destination=" + window);

        List<String> overlapping =
                new ArrayList<>(List.of("A", "B", "C", "D", "E"));
        List<String> snapshot =
                new ArrayList<>(overlapping.subList(0, 3));
        Collections.copy(overlapping.subList(1, 4), snapshot);
        System.out.println("overlap.withSnapshot=" + overlapping);

        List<String> linked =
                new LinkedList<>(List.of("x", "y", "tail"));
        Collections.copy(linked, source);
        System.out.println("linked.destination=" + linked);

        List<String> keep = new ArrayList<>(List.of("keep"));
        Collections.copy(keep, Collections.<String>emptyList());
        System.out.println("emptySource.destination=" + keep);
        rejects("null.destination", NullPointerException.class,
                () -> Collections.copy((List<String>) null, source));
        rejects("null.source", NullPointerException.class,
                () -> Collections.copy(keep, (List<String>) null));
    }
}
~~~

Biên dịch và chạy tại thư mục chứa tệp:

~~~shell
javac --release 17 -encoding UTF-8 ListCopyDemo.java
java ListCopyDemo
~~~

Cần JDK 17 trở lên cho lệnh biên dịch này. Mã đã được biên dịch với `--release 17` và chạy trên OpenJDK 24.0.2, thoát thành công. Stdout chính xác:

~~~text
prefix.destination=[A, B, tail2, tail3]
prefix.size=4
prefix.sameObject=true
prefix.afterShortSource=[Z, B, tail2, tail3]
source.after=[A, B]
capacity.size=0
capacity.copy=IndexOutOfBoundsException
tooSmall.copy=IndexOutOfBoundsException
readyTarget=[A, B]
readonly.copy=UnsupportedOperationException
nCopies.copy=UnsupportedOperationException
fixed.array=[A, B, keep]
fresh.editable=[A, B, C]
append.result=[old, tail, A, B]
numbers.destination=[7, 8, 2.5]
boxes.sameElement=true
boxes.source=[stock:2]
boxes.destination=[stock:2]
boxes.fresh=[stock:2]
boxes.readonly=[stock:2]
boxes.afterDestinationReplace=[local:9]
boxes.sourceAfterReplace=[stock:2]
nullable.destination=[null, N, tail]
nullable.copyOf=NullPointerException
window.destination=[L, A, B, R]
overlap.withSnapshot=[A, A, B, C, E]
linked.destination=[A, B, tail]
emptySource.destination=[keep]
null.destination=NullPointerException
null.source=NullPointerException
~~~

### Đọc các nhóm kết quả

**`prefix`:** copy hai phần tử thay đúng hai vị trí đầu trong đích bốn phần tử. Size vẫn 4 và biến alias vẫn trỏ tới cùng đích. Copy nguồn chỉ có Z tiếp theo không xóa B hay các ô đuôi.

**`source.after`:** nguồn độc lập có thứ tự và nội dung ban đầu. Chương trình không tráo hai tham số.

**`capacity` và `tooSmall`:** capacity bằng độ dài nguồn nhưng size 0 vẫn không đủ. Đích có một phần tử cho nguồn hai phần tử cũng quá ngắn. Cả hai kiểm tra kích thước tách biệt khỏi lỗi quyền sửa.

**`readyTarget`:** bản `ArrayList` tạo từ các ô ban đầu vừa đủ số vị trí vừa hỗ trợ thay. `readonly.copy` và `nCopies.copy` có đủ size nhưng từ chối ghi.

**`fixed.array`:** đích kích thước cố định vẫn nhận dữ liệu vì cho thay phần tử. Dòng in mảng xác nhận tác động lên đối tượng nền của view.

**`fresh` và `append`:** một thao tác tạo bản làm việc mới, thao tác còn lại nối thêm nguồn vào đích cũ. Không thao tác nào có cùng hậu điều kiện với ghi đè đoạn đầu của `copy`.

**`numbers`:** chữ ký generic cho phép nguồn số nguyên vào đích kiểu `Number`. Phần đuôi `2.5` vẫn còn.

**`boxes`:** nguồn và đích giữ cùng phần tử, được xác nhận bằng so sánh tham chiếu phần tử trong thí nghiệm. Sửa count xuất hiện qua cả bản tạo bằng constructor lẫn list không sửa được. Thay ô đích bằng Box mới chỉ đổi ô ở đích riêng.

**`nullable`:** phần tử `null` được đưa vào `ArrayList`, còn factory `List.copyOf` từ chối nguồn có `null`. Quyền sửa và chính sách phần tử là các hợp đồng khác nhau.

**`window` và `overlap`:** view đích thay đúng đoạn của list gốc. Trường hợp chồng lấp dùng bản chụp nguồn tách biệt nên ghi đúng dữ liệu ban đầu đã chọn.

**`linked`:** đích không bắt buộc là `ArrayList`; `LinkedList` có đủ vị trí và hỗ trợ thay cũng dùng được. Dòng này kiểm tra nội dung, không phải phép đo thời gian.

**`emptySource` và các dòng `null`:** nguồn rỗng không làm rỗng đích; thiếu chính đối tượng nguồn/đích bị báo bằng ngoại lệ.

## 10. Áp dụng và chi phí

### Chọn copy khi đích tồn tại là một phần của yêu cầu

Nếu đã có vùng vị trí cần cập nhật và phải giữ nguyên đối tượng đích, `Collections.copy` có ý nghĩa trực tiếp. Phần còn lại của đích giữ nguyên là một bảo đảm cần được chủ ý sử dụng.

Nếu bạn vừa tạo một đích mới bằng các ô giả rồi copy chỉ để trả một list mới giống nguồn, `new ArrayList<>(source)` thường thể hiện ý định dễ hơn. Không cần tối ưu bằng một chuỗi chuẩn bị phức tạp khi chưa có yêu cầu giữ đích.

### Dữ liệu ngắn hơn lần trước cần một quy tắc xử lý đuôi

Giả sử đích được dùng cho một đợt ba kết quả rồi đợt sau chỉ có một kết quả. Copy đợt hai sẽ không tự xóa hai ô cũ.

Có thể thiết kế một vùng có độ dài cố định và quản lý riêng số ô có dữ liệu hợp lệ. Cũng có thể cần thay toàn bộ danh sách và size để phản ánh đúng đợt kết quả mới. Hai mô hình khác nhau; đừng để một đoạn đuôi vô tình quyết định hành vi sản phẩm.

Nếu muốn xóa và thêm lại trên cùng list, phải biết đích có hỗ trợ các thao tác cấu trúc ấy không và ai quan sát các trạng thái trung gian. Đó không là một biến thể tự động của `Collections.copy`.

### Công việc tăng theo số phần tử nguồn

`Collections.copy` được tài liệu mô tả chạy tuyến tính. Với các list chuẩn và phép truy cập/thay thông thường, việc chuyển n phần tử phải xử lý n giá trị tham chiếu.

Không cần clone các đối tượng phần tử để hoàn thành hợp đồng này. Nếu bạn bổ sung một bước chuyển đổi hoặc sao chép sâu theo mô hình, chi phí ấy là phần việc khác.

Các lớp list có cách truy cập khác nhau. `ArrayList` có truy cập theo vị trí hằng thời gian; `LinkedList` phải đi qua nút cho truy cập bằng chỉ số. Không tự thay tiện ích bằng một vòng `get(i)`/`set(i)` rồi giả định mọi kiểu list đều có chi phí như nhau. [ArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html), [LinkedList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedList.html).

Với list tùy chỉnh có cách đọc/ghi tốn kém, cần xét chi phí của các thao tác nó cung cấp. Tên API không làm biến mất chi phí của đích hoặc nguồn.

## 11. Cách kiểm tra một lời gọi copy

Trước hết, viết trạng thái mong muốn của đích sau thao tác. Nếu mong muốn là “nối dữ liệu”, “tạo list mới” hoặc “thu nhỏ đích theo nguồn”, hãy nhận ra rằng đó không phải hậu điều kiện riêng của `Collections.copy`.

Sau đó kiểm tra các thông tin thực sự quyết định:

1. Hai tham số có đúng hướng đích–nguồn không?
2. Đích có ít nhất `source.size()` phần tử thật chưa?
3. Đích có cho thay phần tử và nhận các giá trị nguồn không?
4. Phần đuôi giữ nguyên có đúng với yêu cầu không?
5. Nguồn và đích có cùng nền hoặc bị bên khác sửa trong lúc thao tác không?
6. Chia sẻ đối tượng phần tử có đúng quyền sở hữu cần thiết không?

Trong kiểm thử, đừng chỉ so đoạn đầu. Cần thử đích dài hơn nguồn để phát hiện hiểu sai về đuôi và size; thử capacity-only để phát hiện nhầm sức chứa; thử fixed-size sửa được và list không sửa được để tách quyền thay khỏi khả năng tăng giảm.

Nếu dữ liệu chứa đối tượng sửa được, kiểm tra riêng việc sửa phần tử và việc thay ô. Hai thao tác thể hiện hai quan hệ khác nhau và thường bị gộp dưới từ “copy”.

## 12. Thực hành có đáp án

### Bài 1 — Nguồn hai, đích bốn

Đích là `[p, q, r, s]`, nguồn là `[A, B]`. Cả hai là list độc lập, đích hỗ trợ thay.

**Câu hỏi:** Sau copy, đích và size là gì? Nguồn có bị tiêu thụ hay bị làm rỗng không?

**Đáp án:** Đích là `[A, B, r, s]`, size vẫn 4. Nguồn vẫn có A và B; copy không lấy phần tử ra khỏi nguồn. Hai vị trí cuối giữ nguyên vì nằm ngoài đoạn được ghi.

### Bài 2 — Đã cấp capacity nhưng vẫn lỗi

~~~java
List<Integer> source = List.of(10, 20, 30);
List<Integer> destination = new ArrayList<>(3);
Collections.copy(destination, source);
~~~

**Câu hỏi:** Điều kiện nào chưa đạt? `ensureCapacity(100)` có sửa được điều đó không?

**Đáp án:** Đích có size 0, chưa có ba phần tử thật. Capacity và `ensureCapacity` không tăng size, nên không giải quyết điều kiện. Nếu cần copy vào các ô, tạo đủ phần tử trước. Nếu chỉ muốn list mới, dùng `new ArrayList<>(source)`.

### Bài 3 — Đủ ô nhưng không được ghi

Đích được tạo bằng `Collections.nCopies(3, 0)` và nguồn là `List.of(1, 2, 3)`.

**Câu hỏi:** Có phải đủ size là copy thành công không? Cách tạo nào cho một đích ba ô sửa được?

**Đáp án:** Không. List `nCopies` không hỗ trợ thay nên copy dữ liệu thực sự bị từ chối bằng `UnsupportedOperationException`. Có thể dùng `new ArrayList<>(Collections.nCopies(3, 0))` để vừa có ô vừa sửa được. Vẫn nên dùng constructor từ nguồn nếu mục tiêu chỉ là bản mới giống nguồn.

### Bài 4 — List dựa trên mảng

~~~java
String[] array = {"x", "y", "z"};
Collections.copy(Arrays.asList(array), List.of("A", "B"));
~~~

**Câu hỏi:** Mảng trở thành gì? Vì sao không cần list có khả năng thêm?

**Đáp án:** Mảng là `[A, B, z]`. View cho thay các ô sẵn có và ghi vào cùng mảng; không có bước làm tăng kích thước. Phần tử z giữ nguyên vì nguồn chỉ có hai phần tử.

### Bài 5 — Copy hay addAll?

Đích ban đầu `[old, tail]`, nguồn `[A, B]`.

**Câu hỏi:** So sánh kết quả `Collections.copy(dest, src)` với `dest.addAll(src)` khi thực hiện riêng từ cùng trạng thái ban đầu.

**Đáp án:** Copy cho `[A, B]` với size 2. AddAll cho `[old, tail, A, B]` với size 4. Một bên thay vị trí đã có; bên kia thêm vị trí mới. Không thể đổi qua lại mà không xét mục tiêu nghiệp vụ.

### Bài 6 — Chia sẻ phần tử

Nguồn có một Box với count 1. Copy vào list đích riêng rồi đổi `source.get(0).count` thành 5.

**Câu hỏi:** Đích thấy count nào? Nếu tiếp tục `dest.set(0, new Box("other", 9))` thì Box ở nguồn có tự thành other/9 không?

**Đáp án:** Đích ban đầu thấy count 5 vì giữ cùng Box. Thay ô đích bằng Box mới không thay tham chiếu ở ô nguồn độc lập; nguồn vẫn giữ Box cũ count 5. Muốn phần tử độc lập cần một chiến lược tạo/sao chép Box, không chỉ sao chép list.

### Bài 7 — Ghi đoạn giữa và chồng lấp

List là `[A, B, C, D, E]`. Cần đưa dữ liệu **ban đầu** ở các vị trí 0–2 sang 1–3.

**Câu hỏi:** Cách làm nào tránh nguồn đọc bị việc ghi đích làm đổi? Kết quả mong muốn là gì?

**Đáp án:** Tạo `new ArrayList<>(values.subList(0, 3))` trước, rồi copy từ bản ấy vào `values.subList(1, 4)`. Kết quả là `[A, A, B, C, E]`. Không giả định hai view chồng lấp tự có ngữ nghĩa chụp nguồn ban đầu.

### Bài 8 — Ba API đều có chữ “copy”

Nguồn list có phần tử `null` và một đối tượng sửa được khác. Xét `Collections.copy(dest, src)`, `new ArrayList<>(src)` và `List.copyOf(src)`.

**Câu hỏi:** API nào cần đích tồn tại? API nào từ chối `null`? Có API nào trong ba cách tự nhân bản sâu đối tượng sửa được không?

**Đáp án:** `Collections.copy` cần đích đủ size và cho thay; việc nhận `null` còn theo hợp đồng đích. Constructor `ArrayList` tạo list sửa được mới và có thể giữ `null`. `List.copyOf` từ chối nguồn có phần tử `null`. Không cách nào tự nhân bản sâu đối tượng sửa được; việc đó cần quy tắc riêng của mô hình.

Khi đọc `Collections.copy`, hãy nghĩ đến việc thay một đoạn ô đang tồn tại. Size, quyền `set`, phần đuôi và sự chia sẻ phần tử mới là những thông tin quyết định; chữ “copy” không tự mang theo lời hứa cấp phát list mới, đổi kích thước hay sao chép sâu.
