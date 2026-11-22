# Phân biệt collection không sửa được, kích thước cố định và bất biến sâu

Một danh sách có thể từ chối `add` nhưng vẫn cho `set`. Một danh sách từ chối cả `add`, `remove` và `set` vẫn có thể hiện thêm phần tử sau khi nguồn được sửa. Ngay cả khi danh sách đã tách khỏi nguồn, đối tượng lấy qua `get` vẫn có thể thay đổi.

Ba tình huống ấy nằm ở ba tầng khác nhau: quyền sửa vật chứa, liên kết với dữ liệu bên ngoài và trạng thái của phần tử. Hiểu đúng từng tầng giúp thiết kế kết quả trả về, cấu hình và bản chụp dữ liệu có hợp đồng rõ ràng.

Bài này dùng Java 17 làm mức API tối thiểu. Cần biết `List`, `ArrayList`, tham chiếu đối tượng và ngoại lệ trước khi làm các thí nghiệm. `Map` được dùng ở một ví dụ ngắn để cho thấy cùng cách phân tích áp dụng cho cả khóa và giá trị.

## 1. Bắt đầu từ điều người dùng dữ liệu được phép làm

Giả sử một dịch vụ trả về danh sách mặt hàng. Yêu cầu “chỉ đọc” còn thiếu thông tin. Người nhận có được đổi thứ tự không? Có được thay mặt hàng ở vị trí 0 không? Nếu dịch vụ thêm một mặt hàng sau đó thì danh sách đã trả có nhìn thấy không? Người nhận có được đổi số lượng của chính mặt hàng không?

Hãy xét bốn câu hỏi riêng:

1. **Đổi số lượng phần tử:** có thêm, xóa hoặc làm rỗng vật chứa được không?
2. **Đổi phần tử hoặc vị trí:** có thay `list[i]` bằng tham chiếu khác, sắp xếp lại hoặc thay ánh xạ của map được không?
3. **Nhìn thấy nguồn thay đổi:** kết quả là góc nhìn (view) hay đã giữ riêng thành phần của mình?
4. **Đổi đối tượng bên trong:** phần tử, khóa, giá trị và những đối tượng lồng bên dưới có phương thức sửa trạng thái không?

Đừng gộp tất cả thành một câu “có mutable không?”. Cùng một `List<E>` có thể trả lời khác nhau ở cả bốn câu. Kiểu khai báo `List<E>` chưa diễn đạt các bảo đảm này; người dùng phải biết hợp đồng của cách tạo hoặc phương thức trả kết quả.

Cũng cần tách **quan sát thấy thay đổi** khỏi **tự gọi phương thức sửa**. Khi nguồn của một view được cập nhật, người giữ view có thể quan sát thấy dữ liệu mới dù họ không có quyền sửa qua view.

## 2. Ba khái niệm và một bảng đối chiếu

### Kích thước cố định

Danh sách kích thước cố định (fixed-size list) không cho tăng hoặc giảm số ô chứa phần tử. Điều này chưa quyết định có được thay tham chiếu tại một ô hay không.

`Arrays.asList(array)` là ví dụ điển hình: danh sách dựa trên chính mảng được truyền vào, hỗ trợ thay phần tử và phản ánh thay đổi qua lại với mảng. `add` hoặc `remove` làm đổi kích thước sẽ bị từ chối. Vì thế “fixed-size” mô tả kích thước, không mô tả đầy đủ quyền sửa. [API Arrays.asList, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html#asList(T...)).

### Không sửa được qua API của collection

Collection không sửa được (unmodifiable collection) từ chối các phương thức sửa vật chứa theo hợp đồng của nó. Với list, những thao tác ấy bao gồm thêm, xóa và thay phần tử. Sửa nội dung của đối tượng do `get` trả về là một lời gọi khác, nằm ngoài việc sửa vật chứa.

Định nghĩa của `Collection` cũng phân biệt collection không sửa được và view không sửa được. View có thể nhìn thấy thay đổi ở nguồn; phần tử có thể có trạng thái riêng thay đổi được. Vì vậy chỉ riêng nhãn “unmodifiable” chưa chứng minh bất biến sâu. [Định nghĩa trong Collection, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html#unmodcoll).

### Bất biến sâu

Trong bài này, **bất biến sâu** (deep immutability) nghĩa là sau khi giá trị được xây dựng xong, trạng thái dữ liệu có thể quan sát của nó và của các đối tượng cấu thành giá trị ấy không thể bị sửa qua các tham chiếu được chia sẻ.

Với một `List<List<String>>`, bảo vệ list ngoài là chưa đủ: các list trong cũng phải có trạng thái ổn định. Với `List<Order>`, còn phải xét `Order` chứa gì. Nếu `Order` có danh sách chi tiết, mỗi chi tiết có thể lại chứa đối tượng khác. Phạm vi chứng minh đi theo mô hình dữ liệu, không dừng ở một lần gọi `copyOf`.

Không nhất thiết phải nhân bản mọi đối tượng mới có được bất biến sâu. Có thể chia sẻ an toàn những giá trị vốn đã bất biến, chẳng hạn chuỗi. Điều cần loại bỏ là khả năng sửa trạng thái chung làm thay đổi giá trị đang bảo vệ.

| Cách tạo điển hình | Thêm/xóa qua list | Thay phần tử bằng `set` | Thay đổi cấu trúc nguồn có hiện vào kết quả? | Tự bảo đảm phần tử bất biến sâu? |
| --- | --- | --- | --- | --- |
| `new ArrayList<>(source)` | Có | Có | Không liên kết cấu trúc nguồn | Không |
| `Arrays.asList(array)` | Không đổi kích thước | Có | Có, cùng các ô của mảng | Không |
| `Collections.unmodifiableList(source)` | Không | Không | Có nếu nguồn thay đổi | Không |
| `List.copyOf(source)` | Không | Không | Không phản ánh thay đổi thành phần sau đó ở nguồn | Không |
| `List.of(a, b)` | Không | Không | Không có vật chứa nguồn để theo dõi | Không |
| List ngoài không sửa được, phần tử là giá trị bất biến đã được bảo vệ đầy đủ | Không | Không | Không có đường sửa dữ liệu đã công bố | Có, theo hợp đồng của mô hình ấy |

“Không liên kết cấu trúc nguồn” không có nghĩa mọi đối tượng bên trong đều khác nhau. Ví dụ `new ArrayList<>(source)` vẫn có thể giữ cùng tham chiếu tới từng `Order`. Bảng đang phân biệt vật chứa và dữ liệu bên trong, không khẳng định có sao chép sâu.

Các hàng cũng có thể đồng thời mang nhiều tính chất. Một list không sửa được dĩ nhiên không cho người nhận đổi kích thước qua nó; điều đó không làm `Arrays.asList` trở thành không sửa được, vì list của `Arrays.asList` vẫn hỗ trợ `set`.

## 3. Vì sao kích thước cố định vẫn có thể sửa được?

Mảng có số phần tử cố định nhưng từng ô mảng có thể được gán giá trị khác. Khi một list cung cấp cách truy cập những ô ấy, thay phần tử không đòi tạo thêm hoặc xóa bớt ô.

Đoạn sau là **mã minh họa trong một phương thức**, chưa phải tệp chương trình độc lập:

~~~java
String[] names = {"Lan", "Minh"};
List<String> fixed = Arrays.asList(names);

fixed.set(0, "An");   // Thay tham chiếu tại ô 0.
names[1] = "Binh";    // Sửa cùng vùng lưu phần tử qua mảng.
~~~

`fixed.size()` vẫn là 2. Sau hai phép gán, cả mảng và list biểu diễn hai tên `An`, `Binh`. Không có thao tác thêm phần tử.

Sắp xếp cũng có thể chỉ thay thứ tự các giá trị trong những ô sẵn có. Một danh sách không cần tăng giảm kích thước để được sắp xếp. Chương trình ở phần minh chứng sẽ sắp xếp list do `Arrays.asList` tạo ra và in lại chính mảng.

Điều này giúp giải thích một lỗi thường gặp: nhận `Arrays.asList` rồi gọi `add` vì biến có kiểu `List`. Giao diện có khai báo phương thức không đồng nghĩa mọi đối tượng thực thi đều hỗ trợ thao tác đó. Một số thao tác sửa trong Collections Framework là tùy chọn.

Nếu cần một danh sách có thể thêm/xóa độc lập với mảng, hãy tạo vật chứa có hợp đồng phù hợp:

~~~java
List<String> editable = new ArrayList<>(Arrays.asList(names));
editable.add("Chi");
~~~

Đây vẫn chỉ là sao chép ở tầng danh sách. Với `String`, việc dùng chung phần tử không gây đường sửa nội dung chuỗi; với đối tượng nghiệp vụ sửa được, cần phân tích tiếp.

Không suy diễn rằng tất cả danh sách có cùng kích thước đều có cùng quyền sửa. `List.of("Lan", "Minh")` cũng có hai phần tử nhưng từ chối cả `set`. Số lượng hiện tại, quyền thay phần tử và quyền tăng giảm kích thước là những thông tin khác nhau.

Một chi tiết khi nhận đầu vào từ mảng: `Arrays.asList` nhận các phần tử kiểu tham chiếu. Nếu truyền một `int[]` trực tiếp, kết quả thường là list chứa **một đối tượng mảng `int[]`**, không phải list nhiều `Integer`. Điều đó càng cho thấy phải xác định đúng đối tượng nào đang là “phần tử” trước khi nói đến sao chép và bất biến.

## 4. View chỉ đọc và bản chụp thành phần có mục đích khác nhau

### View không sửa được: người sở hữu nguồn vẫn cập nhật

`Collections.unmodifiableList(source)` trả về view đọc qua danh sách nguồn. Người nhận không được sửa qua list hay iterator của view. Chủ sở hữu nguồn vẫn có thể sửa nguồn và view nhìn thấy thay đổi ấy. [API Collections.unmodifiableList, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableList(java.util.List)).

Ví dụ có ý nghĩa trong một thành phần quản lý lịch tác vụ: bên ngoài được đọc lịch hiện hành, còn thành phần quản lý cập nhật nguồn bằng những phương thức đã kiểm soát. Hợp đồng có thể là “đọc trạng thái hiện tại”, không phải “giữ nguyên lịch tại lúc gọi”.

Mã minh họa:

~~~java
List<String> source = new ArrayList<>(List.of("queued"));
List<String> live = Collections.unmodifiableList(source);

source.add("running");
// live bây giờ biểu diễn [queued, running].
~~~

Nếu tài liệu của phương thức chỉ ghi “trả về list không sửa được”, người nhận chưa thể kết luận việc lưu list ấy trong một báo cáo sẽ giữ nguyên lịch sử. Cần ghi rõ đây là view sống theo nguồn.

Việc bọc cũng không chuyển quyền sở hữu. Nếu hàm tạo lưu trực tiếp list do bên ngoài truyền rồi bọc lại, bên ngoài vẫn giữ một đường sửa nguồn. Từ chối `result.add(...)` chưa loại bỏ đường sửa `input.add(...)`.

### Bản chụp thành phần: không theo nguồn ở tầng ngoài

`List.copyOf(source)` tạo kết quả không sửa được, giữ thứ tự duyệt đầu vào và không phản ánh những thay đổi thành phần sau đó ở collection nguồn. Nó từ chối phần tử `null`. API cho phép tối ưu tái sử dụng một list thích hợp; không dùng `==` hoặc kỳ vọng “luôn cấp phát đối tượng mới” để kiểm tra tính độc lập. [API List.copyOf, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)).

Ở đây “bản chụp thành phần” nói về những tham chiếu có mặt, số lượng và thứ tự của list. Không có lời hứa rằng toàn bộ trạng thái mỗi đối tượng được nhân bản.

~~~java
List<String> source = new ArrayList<>(List.of("queued"));
List<String> saved = List.copyOf(source);

source.add("running");
// saved vẫn biểu diễn [queued].
~~~

Với các phần tử `String`, cách này thường đủ để làm một giá trị danh sách ổn định. Với các phần tử `MutableTask`, thêm một nhiệm vụ mới vào nguồn không làm list đã lưu dài thêm, nhưng sửa một nhiệm vụ vốn được cả hai list cùng tham chiếu vẫn có thể hiện ở cả hai.

Có thể tạo kết quả tương tự về độc lập tầng ngoài bằng cách bọc một bản sao riêng:

~~~java
List<String> saved =
        Collections.unmodifiableList(new ArrayList<>(source));
~~~

Cần bảo đảm không để lộ bản `ArrayList` bên trong. Cách này cũng cần cân nhắc hợp đồng `null`; nó không giống hoàn toàn `List.copyOf`. Lựa chọn phải xuất phát từ yêu cầu API, không phải thay một dòng cho “hiện đại hơn”.

### Một view có thể ổn định nếu nguồn không còn đường sửa

View chỉ đọc không tự bảo đảm bất biến, nhưng cũng không đồng nghĩa nó chắc chắn thay đổi. Nếu nguồn chỉ được giữ kín bên trong và không bao giờ sửa sau khi công bố, view có thể có trạng thái ổn định.

Điều ấy là kết quả của **quản lý quyền sở hữu**, không phải khả năng tự đóng băng của lớp bọc. Khi người duy trì sau này thêm đường sửa nguồn, lời hứa ổn định có thể bị phá vỡ dù dòng `unmodifiableList` vẫn còn nguyên.

Để một API dễ duy trì, hãy chọn rõ một trong hai ý định: cung cấp trạng thái hiện tại có thể cập nhật, hoặc công bố một giá trị đã chốt. Tên phương thức và tài liệu nên thể hiện ý định đó.

## 5. Không sửa vật chứa khác với không sửa phần tử

Xét một mặt hàng có trường `quantity` và danh sách nhãn `tags`:

~~~text
list ngoài
  └── tham chiếu tới mặt hàng
        ├── quantity
        └── tham chiếu tới list nhãn
              └── các String
~~~

Nếu list ngoài không sửa được, người nhận không được bỏ mặt hàng ra khỏi list hoặc thay mặt hàng bằng một đối tượng khác. Nhưng thao tác `item.setQuantity(7)` hướng tới đối tượng mặt hàng. Nó không gọi `list.set` và không cần quyền sửa list ngoài.

Tương tự, `item.getTags().add("sale")` sửa list nhãn. Có ít nhất hai lớp phải phân tích trước khi chạm tới các chuỗi.

Đoạn minh họa này nhấn mạnh điểm nối giữa các lớp:

~~~java
List<StringBuilder> messages =
        List.of(new StringBuilder("draft"));

messages.get(0).append("-edited");
~~~

List vẫn có một phần tử, cùng tham chiếu cũ, cùng vị trí cũ. Đối tượng `StringBuilder` đổi nội dung. Nhận xét “list không sửa được” vẫn đúng; nhận xét “toàn bộ giá trị chắc chắn không thay đổi” thì sai.

Không thể khắc phục bằng cách chỉ bọc list ngoài thêm một lần. Lớp bọc thứ hai không biến `StringBuilder` thành chuỗi bất biến. Phải chuyển phần tử sang kiểu biểu diễn phù hợp, hoặc sao chép và bảo vệ nó theo hợp đồng rõ ràng.

Một phép biến đổi có chủ đích là lấy nội dung của từng `StringBuilder` thành `String` tại thời điểm chốt:

~~~java
List<String> savedMessages = messages.stream()
        .map(StringBuilder::toString)
        .toList();
~~~

Đây là một phép chuyển mô hình dữ liệu, không phải khả năng sao chép sâu tự động của `toList`. Hàm `map` quyết định phần nào được chụp; `toList` chỉ gom kết quả thành list không sửa được.

Trong Java 17, `Stream.toList()` đã có sẵn từ Java 16. Kết quả của nó không sửa được nhưng không có bảo đảm cụ thể về lớp triển khai. [API Stream.toList, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#toList()).

Khi phần tử chứa tài nguyên sống, khóa, luồng xử lý hoặc đối tượng có quan hệ vòng, “sao chép toàn bộ đồ thị” thường không còn là một yêu cầu hiển nhiên. Hãy xác định một giá trị nghiệp vụ cần lưu, chẳng hạn mã mặt hàng, số lượng và nhãn, rồi xây dựng biểu diễn ổn định cho chính giá trị ấy.

## 6. Bảo vệ dữ liệu lồng nhau theo mô hình cụ thể

### Trường hợp hai tầng list chứa chuỗi

Giả sử đầu vào có kiểu `List<List<String>>`. `List.copyOf(input)` chỉ giữ riêng các tham chiếu list con. Mỗi list con vẫn là một đối tượng độc lập có thể được sửa bởi người đang giữ nó.

Nếu hợp đồng yêu cầu đóng băng các nhóm chuỗi, có thể chụp từng list con trước, rồi chụp list ngoài:

~~~java
List<List<String>> groups = input.stream()
        .map(group -> List.copyOf(group))
        .toList();
~~~

Đoạn này là mã minh họa với biến `input` đã tồn tại. Nó giả định nguồn không thay đổi trong quá trình đọc và các list con/phần tử đáp ứng chính sách không `null` của `List.copyOf`.

Vì tầng lá ở đây là `String`, không có đường sửa nội dung chuỗi thông thường. Mỗi list con kết quả không sửa được, list ngoài kết quả không sửa được, và các list nguồn không còn điều khiển thành phần của chúng. Với mô hình hai tầng này, lập luận bất biến đi đến được các lá.

Nếu thay `String` bằng `MutableItem`, cùng đoạn mã không còn đủ. Nó sẽ chốt các tầng list nhưng vẫn chia sẻ mặt hàng. Đừng đặt tên hàm chung chung là `deepCopy` rồi dùng cho mọi kiểu phần tử khi nó chỉ xử lý hai lớp list.

### Trường hợp phần tử là dữ liệu nghiệp vụ

Thay vì cố biến đối tượng có hành vi cập nhật thành bất biến, có thể định nghĩa kiểu dành riêng cho dữ liệu đã chốt:

~~~java
record ItemSnapshot(
        String code,
        int quantity,
        List<String> tags
) {
    ItemSnapshot {
        Objects.requireNonNull(code);
        tags = List.copyOf(tags);
    }
}
~~~

Mã trên là khai báo kiểu minh họa; cần `import java.util.List` và `import java.util.Objects`. Chương trình hoàn chỉnh bên dưới chứa khai báo này và cách dùng.

Lập luận cho mô hình ấy gồm các bước:

- `quantity` là giá trị nguyên, không phải tham chiếu tới một ô số lượng có thể sửa bên ngoài.
- `code` là `String` và được yêu cầu không `null`.
- `tags` được giữ dưới dạng list không sửa được, không theo thành phần của list đầu vào.
- Từng nhãn là `String`. Không còn một đối tượng nhãn sửa được bị chia sẻ.
- Không thêm phương thức nào làm lộ một nguồn sửa được ẩn phía sau các trường này.

Hàm tạo chính là ranh giới nhận dữ liệu. Nếu chỉ có accessor chỉ đọc nhưng hàm tạo vẫn lưu nguyên list đầu vào, người tạo đối tượng vẫn có thể sửa qua list cũ.

Tài liệu về thiết kế đối tượng bất biến nhấn mạnh việc kiểm soát các tham chiếu tới dữ liệu sửa được ở cả đầu vào lẫn đầu ra. Sao chép phòng vệ phải phục vụ mô hình dữ liệu cụ thể. [Hướng dẫn thiết kế đối tượng bất biến của Oracle](https://docs.oracle.com/javase/tutorial/essential/concurrency/imstrat.html).

Không cần trả một bản sao mới của `tags` sau mỗi lần gọi accessor trong mô hình này: bản thân list đã được chốt và lá là chuỗi. Với một trường `byte[]` thì tình huống khác: mảng luôn còn các ô gán được, nên cần sao chép khi nhận vào và khi trả ra, hoặc dùng một kiểu biểu diễn có hợp đồng thích hợp.

### Sao chép sâu và bất biến sâu không đồng nghĩa

Nếu sao chép mặt hàng thành đối tượng mới nhưng đối tượng mới vẫn có setter công khai, người nhận vẫn sửa được bản sao. Đó có thể là bản sao độc lập có thể chỉnh sửa, rất hữu ích cho một biểu mẫu, nhưng chưa phải giá trị bất biến sâu.

Ngược lại, một cấu trúc bất biến sâu có thể chia sẻ rất nhiều phần đã bất biến. Một list chốt các `ItemSnapshot` không nhất thiết phải tạo lại mọi chuỗi. Bảo đảm quan trọng là thay đổi dữ liệu không thể lan qua một phần sửa được đang chia sẻ.

Vì vậy hãy nói chính xác mình cần gì: “bản sao để người nhận sửa riêng” hay “giá trị không được thay đổi sau khi công bố”. Hai mục tiêu dẫn tới cách thiết kế khác nhau.

## 7. `final` và `record` bảo vệ đến đâu?

### `final` khóa biến tham chiếu

~~~java
final List<String> labels = new ArrayList<>();
labels.add("new");
~~~

Đoạn này hợp lệ. `final` ngăn gán `labels` sang một list khác sau khi đã khởi tạo; nó không tước quyền `add` của đối tượng `ArrayList` đang được tham chiếu.

Điều tương tự áp dụng cho `final String[]`: biến luôn giữ cùng mảng nhưng từng ô vẫn có thể được gán lại. Đây là quy tắc ngôn ngữ về biến, không phải bộ đóng băng đối tượng. [JLS 17, mục 4.12.4 về biến final](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.12.4).

Đừng dùng việc thấy nhiều trường `private final` như bằng chứng duy nhất của bất biến sâu. Còn phải xét những đối tượng các trường ấy trỏ tới và các đường truy cập vào chúng.

### `record` không tự sao chép các thành phần

~~~java
record Tags(List<String> values) {
}
~~~

Một `record` như trên nhận và giữ giá trị tham chiếu của thành phần. Nếu bên ngoài giữ list đầu vào, họ vẫn có thể sửa list ấy. Accessor mặc định cũng trả giá trị của thành phần, nên người nhận có thể gọi `values().add(...)` nếu list thực tế hỗ trợ.

API `Record` mô tả record là vật mang dữ liệu bất biến nông; hàm tạo và accessor có thể cần được khai báo để kiểm tra đầu vào hoặc sao chép phòng vệ. [API Record, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Record.html).

Mô hình `ItemSnapshot` đã xử lý vấn đề bằng hàm tạo gọn (compact constructor). Việc viết `tags = List.copyOf(tags)` thay tham số sẽ được dùng để khởi tạo trường. Tuy vậy, bảo đảm sâu đến từ cả kiểu lá `String` và việc chốt list; chỉ riêng cú pháp `record` không làm điều đó.

Một record chứa list phần tử sửa được có thể đổi kết quả `equals` hoặc `hashCode` theo trạng thái các thành phần. Đừng dùng một giá trị như thế làm khóa rồi sửa dữ liệu tham gia so sánh. Tên gọi “record” không loại bỏ nghĩa vụ kiểm soát trạng thái.

## 8. Minh chứng chạy được: kiểm tra từng đường thay đổi

Lưu toàn bộ mã dưới đây vào **`CollectionProtectionDemo.java`**. Chương trình dùng API và cú pháp tương thích Java 17, không cần thư viện ngoài.

`MutableItem` cố ý giữ danh sách nhãn đầu vào để tạo tình huống có dữ liệu chia sẻ. Đây là mô hình dùng cho thí nghiệm. `ItemSnapshot` là biểu diễn đã được bảo vệ của cùng những thông tin được chọn.

Hàm `rejected` chỉ coi một thao tác là bị chặn khi nhận đúng `UnsupportedOperationException`. Nếu thao tác bất ngờ thành công, chương trình dừng bằng `AssertionError`. Tương tự, `rejectsNull` kiểm tra đúng `NullPointerException`. Chương trình không dựa vào thông báo ngoại lệ, tên lớp triển khai nội bộ hay thứ tự duyệt map.

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Iterator;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class CollectionProtectionDemo {
    static final class MutableItem {
        private final String code;
        private int quantity;
        private final List<String> tags;

        MutableItem(String code, int quantity, List<String> tags) {
            this.code = Objects.requireNonNull(code);
            this.quantity = quantity;
            this.tags = Objects.requireNonNull(tags);
        }

        ItemSnapshot snapshot() {
            return new ItemSnapshot(code, quantity, tags);
        }

        @Override
        public String toString() {
            return code + ":" + quantity + ":" + tags;
        }
    }

    record ItemSnapshot(String code, int quantity, List<String> tags) {
        ItemSnapshot {
            Objects.requireNonNull(code);
            tags = List.copyOf(tags);
        }
    }

    record PlainTags(List<String> values) {
    }

    record SafeTags(List<String> values) {
        SafeTags {
            values = List.copyOf(values);
        }
    }

    private static void rejected(String label, Runnable action) {
        try {
            action.run();
            throw new AssertionError(label + " unexpectedly succeeded");
        } catch (UnsupportedOperationException ex) {
            System.out.println(label + "=UnsupportedOperationException");
        }
    }

    private static void rejectsNull(String label, Runnable action) {
        try {
            action.run();
            throw new AssertionError(label + " unexpectedly succeeded");
        } catch (NullPointerException ex) {
            System.out.println(label + "=NullPointerException");
        }
    }

    public static void main(String[] args) {
        String[] words = {"pear", "apple"};
        List<String> fixed = Arrays.asList(words);
        fixed.set(0, "plum");
        System.out.println("array.afterSet=" + Arrays.toString(words));
        words[1] = "apricot";
        System.out.println("fixed.afterArrayEdit=" + fixed);
        Collections.sort(fixed);
        System.out.println("array.afterSort=" + Arrays.toString(words));
        rejected("fixed.add", () -> fixed.add("orange"));
        rejected("fixed.remove", () -> fixed.remove(0));

        List<String> source = new ArrayList<>(List.of("A", "B"));
        List<String> live = Collections.unmodifiableList(source);
        List<String> detached = List.copyOf(source);
        source.set(0, "A2");
        source.add("C");
        System.out.println("live=" + live);
        System.out.println("detached=" + detached);
        rejected("live.set", () -> live.set(0, "X"));
        Iterator<String> iterator = live.iterator();
        iterator.next();
        rejected("live.iterator.remove", iterator::remove);

        List<String> itemTags = new ArrayList<>(List.of("school"));
        MutableItem item = new MutableItem("pen", 2, itemTags);
        List<MutableItem> outer = List.of(item);
        List<ItemSnapshot> snapshots = outer.stream()
                .map(MutableItem::snapshot)
                .toList();
        item.quantity = 7;
        itemTags.add("sale");
        System.out.println("outer.afterItemEdit=" + outer);
        System.out.println("snapshot=" + snapshots);
        rejected("outer.set", () -> outer.set(0, item));
        rejected("snapshot.tags.add",
                () -> snapshots.get(0).tags().add("extra"));

        List<String> inner = new ArrayList<>(List.of("x"));
        List<List<String>> nested = new ArrayList<>();
        nested.add(inner);
        List<List<String>> shallow = List.copyOf(nested);
        List<List<String>> deepForStrings = nested.stream()
                .map(xs -> List.copyOf(xs))
                .toList();
        inner.add("y");
        nested.add(List.of("new"));
        System.out.println("nested.source=" + nested);
        System.out.println("nested.shallow=" + shallow);
        System.out.println("nested.deep=" + deepForStrings);
        rejected("nested.deep.inner.add",
                () -> deepForStrings.get(0).add("z"));

        List<String> incoming = new ArrayList<>(List.of("base"));
        PlainTags plain = new PlainTags(incoming);
        SafeTags safe = new SafeTags(incoming);
        incoming.add("later");
        System.out.println("record.plain=" + plain.values());
        System.out.println("record.safe=" + safe.values());
        rejected("record.safe.accessor.add", () -> safe.values().add("x"));

        final List<String> finalReference = new ArrayList<>();
        finalReference.add("still mutable");
        System.out.println("final.reference=" + finalReference);

        Map<String, List<String>> map =
                Map.of("items", new ArrayList<>(List.of("one")));
        map.get("items").add("two");
        System.out.println("map.value=" + map.get("items"));
        rejected("map.put", () -> map.put("items", List.of("other")));

        List<String> withNull = Arrays.asList("ok", null);
        System.out.println("fixed.null=" + withNull);
        rejectsNull("copyOf.null", () -> List.copyOf(withNull));
        rejectsNull("of.null", () -> List.of("ok", (String) null));

        List<String> streamList = Stream.of("s", "t").toList();
        rejected("stream.set", () -> streamList.set(0, "S"));
        ArrayList<String> editable = Stream.of("s", "t")
                .collect(Collectors.toCollection(ArrayList::new));
        editable.add("u");
        System.out.println("stream.editable=" + editable);
    }
}
~~~

Biên dịch và chạy từ thư mục chứa tệp:

~~~shell
javac --release 17 -encoding UTF-8 CollectionProtectionDemo.java
java CollectionProtectionDemo
~~~

Dùng JDK 17 trở lên để biên dịch. Tùy chọn `--release 17` giới hạn ngôn ngữ và API ở Java 17; nó không biến JDK đang chạy thành JDK 17. Ví dụ đã được biên dịch với tùy chọn trên và chạy trên OpenJDK 24.0.2, thoát thành công với stdout chính xác sau:

~~~text
array.afterSet=[plum, apple]
fixed.afterArrayEdit=[plum, apricot]
array.afterSort=[apricot, plum]
fixed.add=UnsupportedOperationException
fixed.remove=UnsupportedOperationException
live=[A2, B, C]
detached=[A, B]
live.set=UnsupportedOperationException
live.iterator.remove=UnsupportedOperationException
outer.afterItemEdit=[pen:7:[school, sale]]
snapshot=[ItemSnapshot[code=pen, quantity=2, tags=[school]]]
outer.set=UnsupportedOperationException
snapshot.tags.add=UnsupportedOperationException
nested.source=[[x, y], [new]]
nested.shallow=[[x, y]]
nested.deep=[[x]]
nested.deep.inner.add=UnsupportedOperationException
record.plain=[base, later]
record.safe=[base]
record.safe.accessor.add=UnsupportedOperationException
final.reference=[still mutable]
map.value=[one, two]
map.put=UnsupportedOperationException
fixed.null=[ok, null]
copyOf.null=NullPointerException
of.null=NullPointerException
stream.set=UnsupportedOperationException
stream.editable=[s, t, u]
~~~

### Đọc kết quả theo quan hệ nguyên nhân

**Ba dòng đầu:** `fixed.set` đổi mảng, gán vào mảng đổi list, và sắp xếp list đổi thứ tự trong mảng. Kích thước luôn là 2. Hai dòng ngoại lệ kế tiếp xác nhận những thao tác thêm/xóa thực sự bị từ chối.

**`live` và `detached`:** hai kết quả cùng được tạo trước khi nguồn đổi. `live` nhìn thấy cả `A2` và `C`; `detached` vẫn giữ `A` và `B`. Không phải `live` được quyền sửa, mà chủ sở hữu nguồn đã sửa qua một tham chiếu khác. Iterator của view cũng không mở một lối xóa vòng qua lớp bọc.

**`outer.afterItemEdit` và `snapshot`:** list ngoài `outer` không cho `set` nhưng vẫn phản ánh mặt hàng có số lượng 7 và nhãn `sale`. `snapshots` đã lấy số lượng 2 và chốt nhãn từ trước. Như vậy hai kết quả khác nhau ở cách biểu diễn phần tử, không chỉ ở quyền sửa list ngoài.

**Ba dòng `nested`:** nguồn có thêm nhóm mới và list con đầu tiên có thêm `y`. Bản sao nông không nhận nhóm mới nhưng vẫn thấy `y` vì chia sẻ list con. Bản đã chụp từng nhóm giữ `[[x]]`. Thao tác thêm vào list con kết quả bị chặn.

**Hai record:** `PlainTags` theo list đầu vào nên nhìn thấy `later`. `SafeTags` đã chốt list trong hàm tạo nên giữ `[base]`; accessor cũng không cung cấp một list thêm được. Đây là kiểm tra cả đường đầu vào và đường đầu ra của mô hình chứa chuỗi.

**`final.reference`:** một biến `final` vẫn có thể trỏ tới list cho phép thêm. Không có phép gán lại biến trong chương trình.

**Hai dòng `map`:** ánh xạ `"items" → list` không cho thay, nhưng list đang làm giá trị vẫn thêm được `"two"`. Quyền sửa map và quyền sửa đối tượng giá trị là hai quyền khác nhau.

**Các dòng cuối:** `Arrays.asList` có thể chứa `null`, còn `List.copyOf` và `List.of` từ chối `null` trong tình huống thử. Kết quả `Stream.toList` không cho thay phần tử; khi thực sự cần một `ArrayList` chỉnh sửa, chương trình yêu cầu rõ bằng `Collectors.toCollection(ArrayList::new)`.

Không có dòng nào cố sửa nguồn trong khi đang duyệt nó. Kết quả kiểm chứng là hành vi trong một luồng với thứ tự thao tác rõ ràng; không dùng nó để suy ra bảo đảm chụp nguyên tử khi nhiều luồng cùng cập nhật.

## 9. Áp dụng cho `Set`, `Map` và kết quả stream

### Set: không có `set(index)` nhưng phần tử vẫn có trạng thái

Set không có khái niệm vị trí như list. Vì thế sự phân biệt “thay phần tử tại một vị trí” không áp nguyên xi, nhưng việc bảo vệ vật chứa và trạng thái phần tử vẫn tách biệt.

`Set.of` và `Set.copyOf` tạo set không sửa được. Một phần tử sửa được vẫn có thể làm trạng thái quan sát của set thay đổi; đặc biệt phải giữ ổn định những dữ liệu tham gia `equals` và `hashCode` khi phần tử đang ở trong set. [API Set, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html).

Không nên thử rồi ghi nhớ một kết quả cụ thể của `contains` sau khi đã làm biến đổi dữ liệu so sánh của phần tử. Cách đúng là tránh trạng thái ấy: dùng phần tử có định danh ổn định hoặc một giá trị đã chốt.

### Map: bảo vệ ánh xạ không đóng băng khóa hay giá trị

Map không phải kiểu con của `Collection`, nhưng cùng cách suy luận vẫn hữu ích. Không sửa map nghĩa là không thêm/xóa/thay ánh xạ qua API map. Khóa và giá trị có thể chứa dữ liệu riêng.

`Map.of` và `Map.copyOf` tạo map không sửa được, từ chối khóa/giá trị `null`. Chúng không hứa đóng băng đối tượng khóa hay giá trị, cũng không hứa giữ thứ tự duyệt của một `LinkedHashMap` đầu vào. [API Map, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#unmodifiable).

Với `Map<String, List<String>>` dùng làm cấu hình đã chốt, cần bảo vệ mỗi list giá trị rồi mới chốt map ngoài. Nếu cần thứ tự cụ thể khi trình bày, hãy chọn hợp đồng giữ thứ tự phù hợp và kiểm soát nguồn riêng; đừng lấy một kết quả tình cờ của `Map.copyOf` làm bảo đảm.

Nếu khóa là một đối tượng sửa được, bảo vệ map ngoài cũng không ngăn ai đó sửa chính khóa. Đây là một lý do mạnh để dùng khóa mang giá trị ổn định.

### Stream: thao tác gom không quyết định mọi tầng

Đừng đồng nhất ba biểu thức sau:

~~~java
List<String> a = streamA.toList();
List<String> b = streamB.collect(Collectors.toList());
ArrayList<String> c =
        streamC.collect(Collectors.toCollection(ArrayList::new));
~~~

Đây là đoạn minh họa với ba stream độc lập đã tồn tại; một stream đã tiêu thụ không được dùng lại.

- `toList()` của `Stream` có hợp đồng kết quả không sửa được.
- `Collectors.toList()` không bảo đảm tính sửa được hay lớp triển khai của list kết quả.
- `toCollection(ArrayList::new)` yêu cầu rõ kiểu vật chứa có thể chỉnh sửa mà chương trình mong muốn.

Hợp đồng của `Collectors.toList` không cho phép suy ra “luôn là `ArrayList`” từ một lần chạy. [API Collectors, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html#toList()).

Cả ba cách đều chưa tự chuyển `MutableItem` thành `ItemSnapshot`. Phép biến đổi phần tử phải được viết rõ trong `map` hoặc một bước xây dựng dữ liệu tương đương. Cũng không nên suy ra chính sách `null` của mọi cách gom từ chính sách của `List.of`; mỗi API có hợp đồng riêng.

## 10. Chọn bảo đảm theo nhu cầu của API

### Người nhận cần tự chỉnh sửa một bản riêng

Trả một bản sao vật chứa sửa được có thể là lựa chọn đúng. Ví dụ giao diện chỉnh sửa lấy danh sách mã mặt hàng rồi thêm/bớt trong biểu mẫu:

~~~java
List<String> editableCodes = new ArrayList<>(storedCodes);
~~~

Với mã là chuỗi, việc chia sẻ phần tử không tạo đường sửa nội dung mã. Nếu danh sách chứa đối tượng có setter, phải quyết định biểu mẫu có được sửa trực tiếp chúng không. Một bản sao list không tự tạo “phiên chỉnh sửa riêng” cho toàn bộ mô hình.

### Người nhận cần đọc trạng thái hiện tại

View không sửa được có thể phù hợp khi người sở hữu quản lý cập nhật. Tài liệu nên nói rõ kết quả có thể phản ánh cập nhật sau đó, và các quy tắc dùng đồng thời nếu có.

Tên như `currentTasksView` giúp nêu ý định nhưng không thay thế hợp đồng. Người gọi vẫn cần biết vòng đời của nguồn và quyền sửa các phần tử.

### Người nhận cần giá trị đã chốt cho báo cáo hoặc cấu hình

Khi các phần tử đã bất biến, chốt vật chứa thường đủ. Khi phần tử sửa được, hãy ánh xạ sang kiểu dữ liệu chốt như `ItemSnapshot`. Với mô hình đã lồng nhiều tầng, hãy viết quy tắc bảo vệ từng tầng có thể sửa.

Đừng hứa “snapshot” mơ hồ. Có thể chỉ là bản chụp số lượng và thứ tự các tham chiếu; có thể là bản chụp đầy đủ các trường cần cho báo cáo. Nêu rõ những trường nào được chốt sẽ giúp người gọi hiểu và kiểm thử đúng.

### Cần giữ số ô nhưng cho thay giá trị

Một list kích thước cố định phù hợp với thao tác trên các vị trí sẵn có hoặc làm cầu nối với mảng. Không cần chuyển sang một collection không sửa được nếu yêu cầu thật sự vẫn cho thay phần tử.

Điều đáng kiểm tra là thuật toán phía sau đòi quyền gì. Một thuật toán chỉ thay/sắp xếp vị trí có thể làm việc với list kích thước cố định; thuật toán thêm/xóa cần hợp đồng khác.

### Các chi phí phải gắn với việc thật sự làm

Bọc một view không có cùng mục tiêu với duyệt và sao chép dữ liệu. Chốt các nhóm hoặc chuyển mỗi phần tử sang snapshot có chi phí đọc và tạo dữ liệu theo số phần tử, số tầng và lượng thông tin được giữ. Không thể so hiệu năng chỉ bằng số ký tự của lời gọi API.

Chọn đúng bảo đảm trước, rồi đo nếu chi phí có ý nghĩa. Sao chép sâu tùy ý có thể đắt và còn sai về ý nghĩa nghiệp vụ; chốt đúng dữ liệu cần dùng thường dễ giải thích và kiểm chứng hơn.

## 11. Những kết luận cần tránh khi đọc mã “chỉ đọc”

### “Có `UnsupportedOperationException` nghĩa là bất biến”

Ngoại lệ từ `add` chỉ chứng minh thao tác `add` đó bị từ chối trong tình huống đã thử. Nó không chứng minh `set` bị chặn, nguồn không thay đổi hay phần tử bất biến.

Không nên thăm dò quyền sửa bằng cách gọi các thao tác không tạo tác dụng rồi đoán hợp đồng, chẳng hạn xóa một phần tử vốn không có. Một số phương thức tùy chọn có thể không ném ngoại lệ khi không có gì cần thay đổi. Hãy đọc hợp đồng API và kiểm tra các thao tác thực sự liên quan.

### “Cùng kích thước nghĩa là không thay đổi”

Một list có thể giữ nguyên `size()` nhưng đổi toàn bộ tham chiếu và thứ tự. Một map có thể giữ nguyên số khóa nhưng thay các giá trị. Một list có thể giữ nguyên cả tham chiếu mà trạng thái phần tử bên trong vẫn đổi.

Kiểm thử cần quan sát đúng điều API hứa bảo vệ, chẳng hạn nội dung bản báo cáo sau khi nguồn được cập nhật, chứ không chỉ so kích thước.

### “Sao chép xong là bất biến”

`new ArrayList<>(source)` thường được dùng chính vì người nhận muốn tiếp tục sửa bản sao. Tách nguồn và cấm sửa là hai quyết định độc lập.

Nếu cần cấm sửa kết quả, phải chọn vật chứa có hợp đồng tương ứng; nếu cần cấm mọi thay đổi giá trị quan sát, còn phải xử lý phần tử.

### “Bọc list ở getter là bảo vệ xong đối tượng”

Có thể vẫn tồn tại đường sửa từ tham số hàm tạo, một getter khác, một phương thức cập nhật, hoặc một phần tử chứa list lồng bên trong. Kiểm tra cả đầu vào và mọi đường trả dữ liệu.

Với dữ liệu như mảng, sao chép đầu vào mà trả lại chính mảng nội bộ vẫn để lộ đường sửa. Ngược lại, sao chép đầu ra mà giữ nguyên mảng đầu vào vẫn cho người tạo sửa ngầm bên trong.

### “Không sửa được thì an toàn đồng thời”

Một view không sửa được trên nguồn đang được cập nhật vẫn là dữ liệu sống. Một list ngoài không sửa được chứa đối tượng đang bị nhiều luồng sửa vẫn có vấn đề đồng thời ở những đối tượng đó.

Giá trị bất biến sâu giúp chia sẻ dữ liệu dễ hơn vì không cần phối hợp các lần ghi vào chính giá trị ấy sau xây dựng. Tuy vậy vẫn phải công bố tham chiếu đúng và xử lý đúng việc thay toàn bộ phiên bản, các tài nguyên bên ngoài hoặc nhiều thao tác cần thống nhất. [Khái niệm đối tượng bất biến trong tài liệu đồng thời của Oracle](https://docs.oracle.com/javase/tutorial/essential/concurrency/immutable.html).

Gọi `List.copyOf` hoặc lặp để tạo snapshot không tự biến quá trình đọc nhiều đối tượng đang bị sửa thành một giao dịch nguyên tử. Cần một giao thức nhất quán với phía cập nhật, chẳng hạn cùng cơ chế khóa, nguồn có phiên bản hoặc dữ liệu vốn đã chốt.

### “Bất biến sâu nghĩa là không cần nói rõ phạm vi”

Một kết quả có thể chốt thông tin hiển thị nhưng vẫn chỉ giữ mã tham chiếu tới một dữ liệu bên ngoài sẽ đổi. Điều đó không sai nếu hợp đồng chỉ chốt mã và thông tin đã chọn. Nó chỉ sai khi được quảng cáo là đóng băng mọi trạng thái của hệ thống.

Hãy chứng minh trên đồ thị dữ liệu thực sự tạo thành giá trị trả về. Không đưa tài nguyên không thuộc giá trị, như cơ sở dữ liệu sống, vào lời hứa bất biến của một list.

## 12. Thực hành có đáp án

Hãy tự trả lời trước khi đọc phần giải thích. Với mỗi bài, chỉ ra **đường tham chiếu nào** cho phép quan sát hoặc tạo thay đổi, thay vì chỉ gắn nhãn “mutable/immutable”.

### Bài 1 — Không thêm được nhưng vẫn thay được

Đoạn này chạy trong một phương thức, có đủ import:

~~~java
String[] data = {"a", "b"};
List<String> values = Arrays.asList(data);
values.set(1, "B");
~~~

**Câu hỏi:** `data[1]` là gì? `values.add("c")` có được hỗ trợ không? Cần thay cách tạo thế nào nếu người nhận phải thêm phần tử?

**Đáp án:** `data[1]` là `"B"`, vì list dùng các ô của cùng mảng. Thêm làm đổi kích thước bị từ chối bằng `UnsupportedOperationException`. Có thể dùng `new ArrayList<>(Arrays.asList(data))` để có list thêm được và tách cấu trúc khỏi mảng. Vì các phần tử là chuỗi nên không cần nhân bản chuỗi để tránh sửa nội dung.

### Bài 2 — View đổi dù người nhận không sửa

~~~java
List<String> original = new ArrayList<>(List.of("a"));
List<String> result = Collections.unmodifiableList(original);
original.add("b");
~~~

**Câu hỏi:** `result` có bao nhiêu phần tử? Lời hứa nào phù hợp với kết quả này?

**Đáp án:** Có 2 phần tử. `result` đọc qua `original`; cập nhật qua `original` được quan sát qua view. Lời hứa phù hợp là “không sửa qua kết quả, nhìn thấy trạng thái nguồn”. Nếu muốn giữ các chuỗi tại lúc gọi, dùng một bản chụp như `List.copyOf(original)` **tại thời điểm cần chốt**, không phải sau khi đã thêm `b` nếu mục tiêu là dữ liệu trước đó.

### Bài 3 — Bản sao nông giữ nguyên tham chiếu phần tử

~~~java
StringBuilder text = new StringBuilder("a");
List<StringBuilder> source = new ArrayList<>(List.of(text));
List<StringBuilder> saved = List.copyOf(source);
source.clear();
text.append("b");
~~~

**Câu hỏi:** `saved.size()` bằng bao nhiêu? `saved.get(0).toString()` là gì? Làm thế nào để giữ nội dung văn bản ban đầu?

**Đáp án:** Kích thước là 1; văn bản là `"ab"`. `clear` nguồn không đổi thành phần của `saved`, nhưng `text` là đối tượng cùng được chia sẻ. Cần chuyển sang `String` ở thời điểm chốt, chẳng hạn `source.stream().map(StringBuilder::toString).toList()` **trước `clear` và trước `append`**. Sau khi nguồn đã bị làm rỗng, không thể khôi phục nội dung cũ chỉ từ nguồn ấy bằng thao tác sao chép.

### Bài 4 — Đóng băng tầng nào?

~~~java
List<String> row = new ArrayList<>(List.of("x"));
List<List<String>> table = List.of(row);
row.add("y");
~~~

**Câu hỏi:** Giá trị quan sát của `table` là gì? Thay đổi ít nhất về cách xây dựng để giữ nhóm chuỗi ban đầu?

**Đáp án:** `table` biểu diễn `[[x, y]]`. List ngoài không cho thêm/xóa nhưng chia sẻ `row`. Tại thời điểm cần chốt, tạo `List.of(List.copyOf(row))` hoặc, với nhiều nhóm, ánh xạ từng nhóm qua `List.copyOf` rồi gom thành list ngoài không sửa được. Nếu tạo sau khi thêm `y`, bản chốt hợp lệ sẽ chứa `y`; sao chép không quay ngược thời gian.

### Bài 5 — Record nào bảo vệ danh sách nhãn?

So sánh hai khai báo:

~~~java
record DraftLabels(List<String> labels) {
}

record SavedLabels(List<String> labels) {
    SavedLabels {
        labels = List.copyOf(labels);
    }
}
~~~

**Câu hỏi:** Khi đối tượng được tạo từ một `ArrayList<String>`, kiểu nào không theo thay đổi thành phần của list đầu vào? Vì sao kết luận chỉ gắn với kiểu lá `String` ở đây?

**Đáp án:** `SavedLabels` chốt list trong hàm tạo. `DraftLabels` chỉ giữ tham chiếu đầu vào. Với `SavedLabels`, accessor trả list không sửa được và các chuỗi không cho đổi nội dung, nên mô hình này có giá trị ổn định. Nếu đổi thành `List<MutableLabel>`, `copyOf` chưa bảo vệ trạng thái từng nhãn; cần biểu diễn nhãn bất biến hoặc chuyển từng nhãn sang dữ liệu chốt.

### Bài 6 — Sao chép sâu vẫn có thể sửa

Một hàm tạo `new ArrayList<MutableItem>()` và tạo một `MutableItem` mới cho mỗi phần tử. Mỗi mặt hàng mới có list nhãn riêng, nhưng vẫn có setter số lượng và phương thức thêm nhãn.

**Câu hỏi:** Kết quả có độc lập với nguồn không? Có bất biến sâu không? Nếu bọc list ngoài bằng `unmodifiableList` thì sao?

**Đáp án:** Nếu mọi phần sửa được cần tách đã thật sự được sao chép, người nhận có thể có bản độc lập để chỉnh sửa. Nó chưa bất biến sâu vì các đối tượng mới vẫn sửa được. Bọc list ngoài chỉ chặn sửa vật chứa; setter và thêm nhãn trên mặt hàng vẫn còn. Cần chuyển sang một mô hình giá trị không có đường sửa được công bố, hoặc kiểm soát đầy đủ mọi tham chiếu tới phần bên trong.

### Bài 7 — Map không sửa được chứa list sửa được

~~~java
Map<String, List<String>> options =
        Map.of("modes", new ArrayList<>(List.of("fast")));
options.get("modes").add("safe");
~~~

**Câu hỏi:** `options.put("modes", List.of("other"))` và lời gọi `add` trên có cùng đối tượng đích không? Cần làm gì để chốt hai chế độ tại thời điểm tạo?

**Đáp án:** `put` hướng tới map và bị từ chối. `add` hướng tới list giá trị và được hỗ trợ trong ví dụ. Để chốt dữ liệu chuỗi, xây dựng giá trị bằng `List.copyOf(inputModes)` rồi đưa giá trị ấy vào map không sửa được, hoặc dùng `List.of` nếu biết sẵn từng chuỗi. Nếu một danh sách khác vẫn dùng chung đối tượng phần tử sửa được, phải xử lý tầng đó tiếp.

### Bài 8 — Viết hợp đồng trước khi chọn API

Ba phương thức cần trả về:

1. Danh sách mã để người nhận tự thêm/xóa mà không đổi danh sách mã của dịch vụ.
2. Danh sách tác vụ chỉ cho đọc nhưng phải nhìn thấy dịch vụ cập nhật sau đó.
3. Báo cáo mặt hàng giữ nguyên mã, số lượng và nhãn tại lúc chốt.

**Câu hỏi:** Chọn cách tạo phù hợp và nêu một giới hạn của từng cách.

**Đáp án:**

1. Có thể dùng `new ArrayList<>(codes)`. Nó tách vật chứa và cho chỉnh sửa; nếu `codes` có phần tử sửa được thay vì chuỗi thì vẫn cần xét quyền sửa phần tử.
2. Có thể dùng `Collections.unmodifiableList(tasks)`. Nó theo nguồn; phải ghi rõ quyền sửa tác vụ bên trong và quy tắc dùng đồng thời. Không hứa giữ nguyên lịch sử.
3. Chuyển từng mặt hàng thành `ItemSnapshot` với các trường cần báo cáo được bảo vệ, rồi gom thành list không sửa được. Cần bảo đảm việc đọc nguồn để chốt là nhất quán theo yêu cầu nghiệp vụ; các lời gọi sao chép tự chúng không tạo một thời điểm chụp nguyên tử cho toàn hệ thống.

Khi đánh giá một kết quả “chỉ đọc”, hãy lần theo từng đường thay đổi: từ biến đến vật chứa, từ vật chứa đến phần tử, rồi đến dữ liệu lồng bên trong. Một bảo đảm chỉ có ý nghĩa khi chỉ rõ nó chặn đường nào và còn cho phép quan sát thay đổi qua đường nào.
