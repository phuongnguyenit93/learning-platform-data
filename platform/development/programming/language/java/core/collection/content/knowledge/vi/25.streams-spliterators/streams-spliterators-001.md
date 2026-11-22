# Collection lưu dữ liệu còn Stream mô tả quá trình xử lý

## 1. Hai vai trò cần phân biệt

Giả sử ứng dụng đang giữ bốn tên người:

~~~text
[Lan, An, Mai, Bo]
~~~

Ta cần chọn những tên có ít nhất ba ký tự, rồi viết hoa chúng. Có hai việc khác nhau:

- **Giữ dữ liệu:** hiện có những tên nào, theo thứ tự nào, ở vị trí nào.
- **Xử lý dữ liệu:** kiểm tra độ dài, bỏ qua tên không đạt, đổi tên còn lại thành dạng viết hoa và tạo kết quả.

Một `List<String>` là một dạng `Collection` dùng để biểu diễn nhóm phần tử được giữ. Một `Stream<String>` mô tả một chuỗi xử lý trên nguồn phần tử. Stream có thể đọc từ collection đó, nhưng không phải là một danh sách khác vừa được sao chép ra.

Tài liệu Java phân biệt Stream với Collection ở việc Stream không phải cấu trúc lưu các phần tử, có thể xử lý lười, có thể có nguồn không bị chặn trước về số phần tử và chỉ được dùng một lần. [Java SE 17 — java.util.stream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/package-summary.html).

Mô hình khởi đầu:

~~~text
Collection giữ phần tử
        |
        | tạo stream từ nguồn
        v
nguồn -> các bước xử lý -> thao tác kết thúc -> kết quả
~~~

Kết quả cuối có thể là một danh sách mới, một số tổng, một câu trả lời đúng/sai, một phần tử tìm được hoặc tác dụng phụ được yêu cầu. Không phải cứ dùng Stream là phải tạo thêm Collection.

Sau bài này, người học cần đọc được một pipeline theo ba phần, biết khi nào xử lý phần tử bắt đầu, phân biệt nguồn với kết quả, và hiểu vì sao không nên lưu một Stream để duyệt đi duyệt lại như một danh sách.

## 2. Collection là mô hình dữ liệu, Stream là mô hình tính toán

### 2.1. Collection trả lời những câu hỏi về nhóm phần tử

`Collection<E>` là giao diện gốc của hệ phân cấp collection. Các dạng như `List`, `Set` và `Queue` cung cấp những hợp đồng cụ thể hơn. Các phương thức như `size`, `contains` hoặc `iterator` làm việc với nhóm phần tử đang được biểu diễn. Quyền thêm/xóa tùy từng cách cài đặt; không phải mọi Collection đều sửa được. [Java SE 17 — Collection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html).

Ví dụ:

~~~java
List<String> names = new ArrayList<>(List.of("Lan", "An", "Mai", "Bo"));
~~~

`names` giữ bốn tham chiếu chuỗi. Có thể đọc `names.get(0)`, gọi `names.size()`, hoặc tạo nhiều bộ duyệt qua các lần sử dụng.

Nói “Collection lưu dữ liệu” là mô hình phân biệt trách nhiệm, không có nghĩa mỗi đối tượng Collection luôn sở hữu một vùng dữ liệu độc lập. Một khung nhìn như `map.values()` hoặc `list.subList(...)` có thể dùng chung cấu trúc nền. Điều cốt lõi là nó biểu diễn một nhóm phần tử để truy cập, trong khi Stream biểu diễn đường xử lý các phần tử được nguồn cung cấp.

### 2.2. Stream trả lời câu hỏi cần làm gì với các phần tử

~~~java
Stream<String> selected = names.stream()
        .filter(name -> name.length() >= 3)
        .map(name -> name.toUpperCase(Locale.ROOT));
~~~

Đây là đoạn minh họa bên trong một phương thức, cần import `Stream`, `Locale` và các lớp collection liên quan.

`selected` không phải một `List` chứa sẵn `LAN` và `MAI`. Nó mô tả:

1. Lấy phần tử từ `names`.
2. Chỉ đưa tiếp những tên dài ít nhất ba ký tự.
3. Chuyển mỗi tên được đưa tiếp thành chữ hoa.

Chưa có thao tác kết thúc để yêu cầu kết quả. Sau khi bổ sung:

~~~java
List<String> result = selected.toList();
~~~

mới có danh sách kết quả `[LAN, MAI]` cho dữ liệu đã nêu. `result` là đối tượng dữ liệu mới để giữ kết quả; `selected` là pipeline đã được dùng.

### 2.3. Bảng so sánh theo đúng trách nhiệm

| Câu hỏi | Collection | Stream |
| --- | --- | --- |
| Có biểu diễn nhóm dữ liệu để giữ và truy cập không? | Có, theo hợp đồng của loại collection | Lấy phần tử từ nguồn qua một pipeline |
| Có nhất thiết có chỉ số không? | Chỉ một số loại, như List | Không có thao tác `get(index)` của List |
| Có thể yêu cầu xử lý lại cùng nguồn không? | Có thể tạo lượt duyệt mới nếu nguồn còn dùng được | Cần tạo Stream mới; không dùng lại pipeline cũ |
| Có luôn biết sẵn số phần tử không? | Có phương thức size trong hợp đồng Collection | Có thể cần tính, có thể không có giới hạn hữu hạn |
| Lọc có xóa khỏi nguồn không? | Một phép sửa như removeIf có thể xóa nếu được hỗ trợ | filter chọn phần tử cho đường xử lý |
| Kết quả có bắt buộc là một collection không? | Bản thân nó biểu diễn nhóm phần tử | Không; có thể là số, Optional, boolean hoặc kết quả khác |

Không có kết luận rằng Stream “tốt hơn” Collection. Hai vai trò bổ sung nhau: giữ dữ liệu bằng cấu trúc phù hợp, rồi dùng một cách duyệt hoặc tính toán phù hợp để tạo kết quả.

## 3. Một pipeline gồm nguồn, thao tác trung gian và thao tác kết thúc

Xét biểu thức đầy đủ:

~~~java
List<String> result = names.stream()
        .filter(name -> name.length() >= 3)
        .map(name -> name.toUpperCase(Locale.ROOT))
        .toList();
~~~

| Phần | Vai trò trong ví dụ |
| --- | --- |
| `names.stream()` | Tạo Stream tuần tự từ nguồn collection |
| `filter(...)` | Thao tác trung gian chọn những phần tử đi tiếp |
| `map(...)` | Thao tác trung gian tính một giá trị đầu ra cho mỗi phần tử đi tiếp |
| `toList()` | Thao tác kết thúc thu kết quả thành danh sách |

Một pipeline có thể không có thao tác trung gian nào, chẳng hạn `names.stream().count()`. Cũng có thể có nhiều bước lọc, ánh xạ hoặc sắp xếp trước khi kết thúc.

Theo hợp đồng `Stream`, việc tính trên nguồn bắt đầu khi thao tác kết thúc được khởi động; các hàm hành vi của pipeline phải tuân thủ yêu cầu không can thiệp vào nguồn và thường phải không phụ thuộc trạng thái thay đổi bên ngoài. [Java SE 17 — Stream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html).

### Thao tác trung gian không phải một Collection trung gian

Cách nhìn dễ gây nhầm là:

~~~text
lọc xong tạo một List mới
rồi viết hoa toàn bộ List đó
rồi lại tạo một List mới khác
~~~

Đó không phải điều mà mỗi lời gọi `filter` hoặc `map` bắt buộc làm. Chúng xây dựng các giai đoạn trong cùng pipeline. Nhiều giai đoạn có thể được phối hợp khi xử lý phần tử mà không tạo một danh sách đầy đủ sau mỗi giai đoạn.

Tuy nhiên, không được từ đó kết luận mọi pipeline đều không cần bộ nhớ tạm. Một thao tác như `sorted` có thể phải giữ dữ liệu để xác định thứ tự trước khi đưa kết quả đi tiếp. “Stream không phải kho lưu phần tử” và “cách thực hiện thuật toán có thể dùng bộ đệm” là hai nhận định tương thích.

## 4. Tính lười: chưa yêu cầu kết quả thì chưa chạy bước xử lý phần tử

Để quan sát, có thể ghi dấu các lời gọi trong một ví dụ tuần tự:

~~~java
List<String> trace = new ArrayList<>();

Stream<String> plan = names.stream()
        .filter(name -> {
            trace.add("filter:" + name);
            return name.length() >= 3;
        })
        .map(name -> {
            trace.add("map:" + name);
            return name.toUpperCase(Locale.ROOT);
        });
~~~

Ngay sau khi tạo pipeline, `trace` vẫn rỗng. Các lambda chưa được gọi trên phần tử chỉ vì ta đã viết `filter` và `map`.

Khi gọi `plan.toList()`, ví dụ minh chứng cho đường xử lý:

~~~text
Lan -> filter đạt -> map thành LAN -> đưa vào kết quả
An  -> filter không đạt
Mai -> filter đạt -> map thành MAI -> đưa vào kết quả
Bo  -> filter không đạt
~~~

Không có `map:An` hoặc `map:Bo` vì hai phần tử đã bị chặn ở bước lọc. Đường xử lý theo phần tử giúp hiểu việc kết hợp giai đoạn, thay vì tưởng rằng toàn bộ phép lọc luôn phải tạo một tập dữ liệu mới trước khi bắt đầu ánh xạ.

Các dấu ghi trong `trace` chỉ phục vụ quan sát pipeline tuần tự cụ thể ở bài. Chúng không phải mẫu thiết kế để cập nhật trạng thái nghiệp vụ trong lambda; cũng không được đem nguyên ví dụ chứa `ArrayList` ghi dấu sang chạy song song rồi mặc nhiên coi là an toàn.

### Tính lười không có nghĩa là chưa xảy ra bất kỳ việc gì

Các đối tượng pipeline vẫn có thể đã được tạo, tham số vẫn được đánh giá và kiểm tra. Một nguồn I/O có thể đã mở tài nguyên ngay khi tạo Stream, dù chưa đọc hết phần tử.

Ví dụ `Files.lines(path)` trả về Stream gắn với một tệp đang mở. Việc các dòng được đọc lười không cho phép bỏ qua nghĩa vụ đóng tệp. Bởi vậy, phát biểu đúng là các thao tác trung gian không tự thực hiện toàn bộ phép xử lý phần tử, không phải “chưa gọi terminal thì mọi thứ hoàn toàn chưa xảy ra”.

### Lỗi trong hàm xử lý có thể xuất hiện muộn

Đoạn minh họa:

~~~java
Stream<Integer> parsed = List.of("1", "bad").stream()
        .map(Integer::parseInt);
~~~

Tạo pipeline không có nghĩa chuỗi `"bad"` đã được phân tích. Một thao tác kết thúc thật sự cần các giá trị số, chẳng hạn `parsed.mapToInt(Integer::intValue).sum()`, sẽ gặp lỗi khi xử lý dữ liệu không hợp lệ.

Không nên chỉ bắt ngoại lệ quanh chỗ tạo Stream rồi cho rằng đã bao hết lỗi chuyển đổi. Vùng xử lý lỗi phải bao quát nơi pipeline được thực hiện.

## 5. Thao tác kết thúc quyết định kết quả cần tính

Từ cùng một nguồn `names`, có thể đặt những câu hỏi khác nhau:

~~~java
long total = names.stream().count();

long longNameCount = names.stream()
        .filter(name -> name.length() >= 3)
        .count();

int totalLength = names.stream()
        .mapToInt(String::length)
        .sum();
~~~

Với `[Lan, An, Mai, Bo]`, ba kết quả lần lượt là `4`, `2` và `10`. Không cần tạo một danh sách độ dài chỉ để tính tổng. `mapToInt` tạo một `IntStream`, phù hợp phép tính trên các giá trị nguyên thủy.

Một số thao tác kết thúc có thể dừng trước khi xử lý hết nguồn. Ví dụ:

~~~java
String first = names.stream()
        .filter(name -> name.startsWith("M"))
        .findFirst()
        .orElse("none");
~~~

Trong ví dụ tuần tự có thứ tự, khi tìm tới `Mai` thì đã có câu trả lời. Không cần tiếp tục kiểm tra `Bo`. `findFirst` biểu diễn yêu cầu lấy phần tử đầu tiên theo thứ tự gặp của nguồn có thứ tự; `Optional` mô tả khả năng không tìm thấy kết quả.

Vì thế, “có terminal” không đồng nghĩa “mọi phần tử phải qua mọi lambda”. Thuật toán chỉ cần tính đủ thông tin cho kết quả mà hợp đồng yêu cầu.

### count có thể không cần duyệt từng phần tử

Nếu số lượng đã biết và các giai đoạn không thay đổi số phần tử, cách cài đặt có thể tính `count` mà không thực hiện một số bước không ảnh hưởng kết quả. Tài liệu nêu rõ khả năng tối ưu này. [Java SE 17 — Stream.count](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#count()).

Đoạn minh họa không nên dùng cho công việc bắt buộc:

~~~java
long count = names.stream()
        .peek(System.out::println)
        .count();
~~~

Không được đặt một yêu cầu quan trọng như ghi nhận giao dịch, xác thực bắt buộc hoặc cập nhật cơ sở dữ liệu trong `peek` rồi dựa vào `count` để bảo đảm nó chạy. Các dòng in có thể không xuất hiện nếu cách cài đặt suy ra số lượng mà không cần duyệt.

Nếu mục đích chính là thực hiện hành động trên từng phần tử, dùng một thao tác được thiết kế cho việc đó, hoặc một vòng lặp rõ ràng. Tối ưu của Stream là một phần lý do cần tách biến đổi dữ liệu khỏi các tác dụng phụ không liên quan đến kết quả.

## 6. Một Stream là một lượt xử lý, không phải công thức dùng lại tự do

Sai lầm phổ biến:

~~~java
Stream<String> selected = names.stream()
        .filter(name -> name.length() >= 3);

long count = selected.count();
List<String> list = selected.toList();
~~~

Lời gọi `count` đã dùng pipeline. Không được dùng lại `selected` cho `toList`. Trong chương trình minh chứng, việc dùng lại bị phát hiện và gây `IllegalStateException`.

Không nên dùng ngoại lệ làm cơ chế kiểm tra xem Stream còn dùng được hay không. Hợp đồng cấm việc tái sử dụng; một cách cài đặt không nhất thiết phát hiện được mọi cách dùng lại. Khi đã chuyển pipeline cho một thao tác kết thúc, hãy coi nó đã được tiêu thụ.

Cũng không thể tách hai nhánh từ cùng một Stream như tách từ một Collection:

~~~java
Stream<String> base = names.stream();
Stream<String> a = base.filter(name -> name.startsWith("L"));
// Tiếp tục tạo nhánh khác từ base không phải cách tái sử dụng hợp lệ.
~~~

Các bước trong pipeline liên kết với nhau. Biến `base` không trở thành một kho dữ liệu chung cho nhiều nhánh truy vấn độc lập.

### Cách 1: tạo Stream mới từ nguồn

~~~java
long count = names.stream()
        .filter(name -> name.length() >= 3)
        .count();

List<String> list = names.stream()
        .filter(name -> name.length() >= 3)
        .toList();
~~~

Hai lượt đọc lại nguồn. Nếu nguồn thay đổi giữa hai lượt hoặc phép xử lý đắt, hai kết quả hoặc chi phí có thể khác điều người viết mong muốn.

### Cách 2: giữ kết quả đã tính

~~~java
List<String> list = names.stream()
        .filter(name -> name.length() >= 3)
        .toList();

int count = list.size();
~~~

Bây giờ dữ liệu cần giữ nằm trong `list`. Khi cần dùng lại nhiều lần, một Collection kết quả thường diễn tả yêu cầu rõ hơn việc cố giữ một Stream đã tiêu thụ.

### Cách 3: giữ hàm tạo pipeline mới

~~~java
Supplier<Stream<String>> selectedNames =
        () -> names.stream().filter(name -> name.length() >= 3);

long count = selectedNames.get().count();
List<String> list = selectedNames.get().toList();
~~~

Ở đây mỗi lời gọi `get` tạo một Stream mới vì thân lambda gọi lại `names.stream()`. Điều đó do cách viết lambda này, không phải bảo đảm chung của mọi `Supplier`. Hợp đồng `Supplier` không bắt buộc luôn trả đối tượng mới. [Java SE 17 — Supplier](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/Supplier.html).

Một supplier chỉ trả lại cùng một Stream đã tạo sẵn vẫn có lỗi tái sử dụng. Giữ được “công thức” nghĩa là giữ một hàm thực sự dựng lượt xử lý mới, không phải đổi tên biến chứa pipeline cũ.

## 7. Stream không phải bản chụp tự động của Collection

Trong ví dụ với `ArrayList`:

~~~java
List<String> values = new ArrayList<>(List.of("A"));
Stream<String> delayed = values.stream().filter(value -> true);

values.add("B");
List<String> result = delayed.toList();
~~~

Kết quả là `[A, B]`. Tạo Stream trước khi thêm `B` không tự sao chép mảng dữ liệu của `ArrayList` để giữ phiên bản `[A]`.

Các nguồn JDK được thiết kế phù hợp có thể phản ánh thay đổi trước khi thao tác kết thúc bắt đầu; đây là điều được mô tả trong phần không can thiệp vào nguồn của thư viện Stream. Không suy ra cùng hành vi cho mọi nguồn tùy biến hoặc cho việc sửa nguồn trong lúc đang xử lý. [Java SE 17 — Non-interference](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/package-summary.html#NonInterference).

Sau khi đã thu thành `result`, nếu thêm `C` vào `values`, các vị trí của `result` vẫn là `[A, B]`. Một Stream mới đọc lại `values` có thể cho `[A, B, C]`.

Phân biệt ba thời điểm:

| Thời điểm | Đối tượng đang có |
| --- | --- |
| Sau khi tạo nguồn | Collection chứa dữ liệu |
| Sau khi dựng pipeline, chưa chạy terminal | Mô tả xử lý gắn với nguồn; không tự có bản sao kết quả |
| Sau khi thu thành danh sách | Collection kết quả giữ các phần tử đã thu trong lần xử lý ấy |

Nếu cần cố định dữ liệu trước khi xây dựng một lượt tính toán, hãy chọn cách sao chép phù hợp. Một bản sao cấu trúc chỉ tách các vị trí của collection; phần tử là đối tượng sửa được vẫn có thể dùng chung. Nếu có truy cập đồng thời, cả thời điểm sao chép và mức nhất quán của nguồn đều cần được thiết kế riêng.

## 8. filter và map không tự sửa nguồn

Với nguồn:

~~~text
[Lan, An, Mai, Bo]
~~~

pipeline lọc tên dài rồi viết hoa có thể trả:

~~~text
[LAN, MAI]
~~~

Nguồn không trở thành `[LAN, MAI]` chỉ vì đã dùng `filter` và `map`. `filter` quyết định phần tử nào đi tiếp; `map` tính giá trị đầu ra. Chúng không có nghĩa “xóa phần tử nguồn” hoặc “gán phần tử mới vào nguồn”.

Đối chiếu:

| Yêu cầu | Cách diễn tả |
| --- | --- |
| Tạo kết quả gồm các phần tử đạt điều kiện | Stream `filter` rồi thu kết quả |
| Xóa phần tử không đạt khỏi một Collection sửa được | Phép sửa như `removeIf` với điều kiện tương ứng |
| Tính giá trị mới cho kết quả | Stream `map` |
| Thay các vị trí của một List sửa được | Phép sửa như `replaceAll`, theo hợp đồng của List |

Lambda vẫn là mã Java và có thể tự viết ra tác dụng phụ. Nếu trong `map` gọi setter của đối tượng nguồn, đối tượng đó có thể bị sửa. Khi ấy chính mã bên trong lambda làm thay đổi, không phải một bảo đảm rằng “Stream sẽ tự biến nguồn thành đầu ra”.

Không nên viết:

~~~java
// Minh họa một cách làm sai với nguồn ArrayList đang được duyệt.
names.stream().forEach(name -> names.remove(name));
~~~

Đây là can thiệp vào nguồn trong lúc xử lý, kể cả khi Stream đang chạy tuần tự. Có thể gây ngoại lệ hoặc kết quả không phù hợp hợp đồng; không được dựa vào việc một lần chạy chưa ném lỗi để coi là hợp lệ.

Nếu cần tạo một danh sách mới, hãy thu kết quả. Nếu cần xóa tại chỗ, dùng thao tác sửa có hợp đồng phù hợp hoặc bộ duyệt theo đúng quy tắc của cấu trúc nguồn. Việc chọn đúng mô hình giúp tránh trộn lẫn giữ dữ liệu và mô tả biến đổi.

## 9. Giữ kết quả cũng cần chọn quyền sửa và mức sao chép

`Stream.toList()` trả về danh sách không cho sửa qua các thao tác thay đổi danh sách. Nó không có nghĩa là một `ArrayList` sửa được. [Java SE 17 — Stream.toList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#toList()).

Nếu cần kết quả thêm/xóa được:

~~~java
List<String> editable = names.stream()
        .filter(name -> name.length() >= 3)
        .collect(Collectors.toCollection(ArrayList::new));
~~~

`Collectors.toCollection` cho chọn cấu trúc đích rõ ràng. [Java SE 17 — Collectors.toCollection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html#toCollection(java.util.function.Supplier)).

Sau đó `editable.add("NEW")` chỉ thêm vào kết quả, không thêm tên vào `names`. Cấu trúc kết quả và cấu trúc nguồn là hai đối tượng có những vị trí riêng.

Nhưng nếu phần tử là đối tượng có trạng thái sửa được:

~~~java
StringBuilder item = new StringBuilder("seed");
List<StringBuilder> source = List.of(item);
List<StringBuilder> result = source.stream().toList();

result.get(0).append("!");
~~~

`source.get(0)` cũng biểu diễn `seed!`. Cả hai nơi giữ tham chiếu tới cùng `StringBuilder`. Danh sách kết quả không cho thêm/xóa vẫn có thể chứa đối tượng có trạng thái sửa được.

Do đó, “không sửa nguồn bằng phép lọc/ánh xạ thông thường” không đồng nghĩa “đầu ra là bản sao sâu không liên quan gì đến đầu vào”. Muốn biến thành dữ liệu độc lập ở cấp đối tượng, phải thực hiện phép sao chép hoặc tạo đối tượng đầu ra phù hợp.

## 10. Stream có thể có nguồn không phải Collection

Stream còn có thể xuất phát từ mảng, bộ sinh giá trị, khoảng số hoặc tài nguyên I/O. Không cần tạo sẵn một danh sách mới để làm nguồn cho mọi bài toán.

Ví dụ:

~~~java
List<Integer> firstFour = Stream.iterate(1, n -> n + 1)
        .limit(4)
        .toList();
~~~

Kết quả là `[1, 2, 3, 4]`. Nguồn `iterate` không cần giữ trước một danh sách chứa tất cả các số sẽ được sinh. Pipeline chỉ lấy đủ số phần tử mà yêu cầu kết quả cần.

Từ đây xuất hiện sự khác biệt quan trọng: Collection có kích thước hữu hạn trong mô hình của nó, nhưng một nguồn Stream có thể tiếp tục sinh phần tử mà không có điểm dừng được xác định trước.

Không phải cứ đặt `limit` ở đâu đó là mọi pipeline đều chắc chắn kết thúc. Một bước lọc trước đó có thể không bao giờ đưa ra phần tử để `limit` đếm. Một bước sắp xếp trên nguồn vô hạn cũng không thể hoàn tất việc nhận toàn bộ đầu vào để quyết định thứ tự đầy đủ.

Vì vậy, khi nguồn có thể không hữu hạn, hãy suy nghĩ theo dòng dữ liệu: bước nào cần đợi bao nhiêu đầu vào, bước nào tạo được đầu ra, và điều kiện dừng có thực sự đạt được không. Đây là hệ quả của mô hình xử lý, không phải vấn đề một danh sách lớn hay nhỏ.

## 11. Không suy ra hiệu năng chỉ từ chữ Stream

Một pipeline lọc–ánh xạ–tính tổng có thể kết hợp các bước và tránh tạo các danh sách trung gian đầy đủ. Nhưng Stream vẫn có chi phí quản lý pipeline, lời gọi hàm và những yêu cầu riêng của từng phép xử lý.

`sorted` có thể cần bộ đệm. `distinct` có thể cần giữ thông tin những giá trị đã gặp. Thu kết quả bằng `toList` vẫn phải giữ dữ liệu kết quả. Nếu đầu ra có hàng triệu phần tử thì đổi cách viết vòng lặp sang Stream không làm dữ liệu đầu ra tự biến mất khỏi bộ nhớ.

Cũng không có bảo đảm rằng dùng `parallelStream` luôn nhanh hơn. Chi phí chia việc, nguồn dữ liệu, thứ tự, phép gộp và công việc trên mỗi phần tử đều ảnh hưởng kết quả. Đặc biệt, viết lambda sửa một danh sách dùng chung từ nhiều luồng không được làm an toàn chỉ bằng cách gọi `parallel`.

Với bài toán đơn giản, một vòng lặp có thể dễ hiểu hơn. Với một chuỗi lọc và tính kết quả rõ ràng, Stream có thể diễn tả ý định tốt. Chọn cách viết dựa trên hợp đồng, độ rõ và phép đo phù hợp nếu hiệu năng là yêu cầu thật sự.

### Spliterator nằm ở ranh giới cung cấp phần tử

Trong nhóm kiến thức này, có thể hiểu `Spliterator` là một cơ chế để duyệt nguồn và, khi phù hợp, chia nguồn thành các phần. `Collection.stream()` dùng cơ chế của nguồn để xây dựng Stream tuần tự. [Java SE 17 — Collection.stream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html#stream()).

Nó không biến Stream thành kho lưu phần tử. Nguồn vẫn cung cấp dữ liệu; pipeline vẫn mô tả các bước xử lý. Việc một nguồn có thể chia ra không đồng nghĩa mọi pipeline phải chạy song song hoặc mọi thao tác có thể bỏ qua yêu cầu thứ tự.

`BaseStream.iterator()` và `spliterator()` là các terminal đặc biệt trao quyền duyệt thủ công cho bên gọi. Trong các trường hợp ấy, việc lấy từng phần tử tiếp tục qua bộ duyệt được trả về, thay vì terminal phải xử lý xong mọi dữ liệu trước khi trả về. Bài dùng các terminal thông thường như `toList`, `count`, `sum` và `findFirst` để quan sát mô hình thực hiện.

## 12. Tiêu thụ Stream và đóng tài nguyên là hai việc

Thao tác kết thúc dùng pipeline để tính kết quả. Đóng Stream gọi các hàm xử lý đóng và giải phóng tài nguyên theo nguồn. Hai việc này không được coi là đồng nghĩa.

`BaseStream` triển khai `AutoCloseable`; các hàm được đăng ký bằng `onClose` chạy khi Stream được đóng. [Java SE 17 — BaseStream.close](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/BaseStream.html#close()).

Trong phần minh chứng, `count` hoàn tất nhưng hàm `onClose` chưa chạy cho đến khi thoát `try-with-resources`. Đây là cách quan sát sự khác nhau mà không cần mở một tệp thật.

Stream tạo từ Collection trong bộ nhớ thường không mang tài nguyên I/O cần đóng. Với nguồn như `Files.lines`, phải tuân thủ hợp đồng tài nguyên của phương thức:

~~~java
// Minh họa bên trong một phương thức có xử lý IOException.
// path là Path do ứng dụng cung cấp.
try (Stream<String> lines = Files.lines(path)) {
    long nonBlank = lines.filter(line -> !line.isBlank()).count();
    System.out.println(nonBlank);
}
~~~

Cần import `java.nio.file.Files`, `java.util.stream.Stream` và xử lý ngoại lệ I/O phù hợp. Đây là đoạn minh họa phụ thuộc tệp đầu vào, không có stdout cố định như chương trình độc lập phía dưới.

`Files.lines` đọc các dòng lười và giữ tham chiếu tới tệp đang mở; đóng Stream sẽ đóng tệp. Tài liệu yêu cầu dùng `try-with-resources` hoặc cơ chế tương đương để đóng kịp thời. [Java SE 17 — Files.lines](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#lines(java.nio.file.Path)).

Không trả một Stream của tệp ra khỏi khối đã đóng rồi yêu cầu nơi khác đọc nó. Nếu API trả Stream gắn tài nguyên cho bên gọi, quyền sở hữu và trách nhiệm đóng phải được công bố rõ ràng.

## 13. Chương trình minh chứng đầy đủ

Lưu mã sau thành **CollectionAndStreamDemo.java**. Chương trình dùng API tương thích Java 17, không cần thư viện ngoài và không đọc/ghi tệp.

Các danh sách `trace`, `checked` và `lifecycle` chỉ ghi dấu cho các ví dụ quan sát tuần tự. Kết quả không phải bảo đảm về thứ tự tác dụng phụ của một pipeline song song hoặc về số lần gọi lambda trong mọi phép tối ưu.

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.function.Supplier;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class CollectionAndStreamDemo {
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

    public static void main(String[] args) {
        List<String> names = new ArrayList<>(List.of("Lan", "An", "Mai", "Bo"));
        List<String> trace = new ArrayList<>();

        Stream<String> plan = names.stream()
                .filter(name -> {
                    trace.add("filter:" + name);
                    return name.length() >= 3;
                })
                .map(name -> {
                    trace.add("map:" + name);
                    return name.toUpperCase(Locale.ROOT);
                });

        System.out.println("before-terminal=" + trace);
        List<String> result = plan.toList();
        System.out.println("result=" + result);
        System.out.println("after-terminal=" + trace);
        System.out.println("source=" + names);
        rejects("reuse-plan", IllegalStateException.class, () -> plan.count());

        System.out.println("fresh-count=" + names.stream().count());
        System.out.println("long-name-count="
                + names.stream().filter(name -> name.length() >= 3).count());
        System.out.println("total-length=" + names.stream().mapToInt(String::length).sum());

        Supplier<Stream<String>> longNames =
                () -> names.stream().filter(name -> name.length() >= 3);
        System.out.println("factory-count=" + longNames.get().count());
        System.out.println("factory-list=" + longNames.get().toList());

        List<String> changing = new ArrayList<>(List.of("A"));
        Stream<String> delayed = changing.stream().filter(value -> true);
        changing.add("B");
        List<String> captured = delayed.toList();
        System.out.println("before-start-change=" + captured);
        changing.add("C");
        System.out.println("materialized-result=" + captured);
        System.out.println("new-query=" + changing.stream().toList());

        List<String> checked = new ArrayList<>();
        String first = names.stream()
                .filter(name -> {
                    checked.add(name);
                    return name.startsWith("M");
                })
                .findFirst()
                .orElse("none");
        System.out.println("first-match=" + first);
        System.out.println("checked=" + checked);

        List<Integer> generated = Stream.iterate(1, n -> n + 1)
                .limit(4)
                .toList();
        System.out.println("generated=" + generated);

        rejects("result-add", UnsupportedOperationException.class, () -> result.add("NEW"));
        List<String> editable = names.stream()
                .filter(name -> name.length() >= 3)
                .collect(Collectors.toCollection(ArrayList::new));
        editable.add("NEW");
        System.out.println("editable=" + editable);
        System.out.println("source-still=" + names);

        StringBuilder item = new StringBuilder("seed");
        List<StringBuilder> objects = List.of(item);
        List<StringBuilder> objectResult = objects.stream().toList();
        objectResult.get(0).append("!");
        System.out.println("shared-object=" + objects.get(0));

        List<String> lifecycle = new ArrayList<>();
        try (Stream<String> closable = Stream.of("A")
                .onClose(() -> lifecycle.add("closed"))) {
            System.out.println("resource-count=" + closable.count());
            System.out.println("after-terminal-close=" + lifecycle);
        }
        System.out.println("after-close=" + lifecycle);
    }
}
~~~

Biên dịch và chạy:

~~~shell
javac --release 17 -encoding UTF-8 CollectionAndStreamDemo.java
java CollectionAndStreamDemo
~~~

Stdout chính xác:

~~~text
before-terminal=[]
result=[LAN, MAI]
after-terminal=[filter:Lan, map:Lan, filter:An, filter:Mai, map:Mai, filter:Bo]
source=[Lan, An, Mai, Bo]
reuse-plan -> IllegalStateException
fresh-count=4
long-name-count=2
total-length=10
factory-count=2
factory-list=[Lan, Mai]
before-start-change=[A, B]
materialized-result=[A, B]
new-query=[A, B, C]
first-match=Mai
checked=[Lan, An, Mai]
generated=[1, 2, 3, 4]
result-add -> UnsupportedOperationException
editable=[Lan, Mai, NEW]
source-still=[Lan, An, Mai, Bo]
shared-object=seed!
resource-count=1
after-terminal-close=[]
after-close=[closed]
~~~

Mã đã biên dịch với `--release 17` và chạy trên JDK 24.0.2. Cờ biên dịch xác minh mức ngôn ngữ/API Java 17; chương trình không được tuyên bố là đã chạy trên JVM 17.

Đối chiếu theo nhóm:

- `before-terminal` rỗng, còn `after-terminal` ghi các bước đã chạy khi lấy kết quả.
- `result` có hai chuỗi viết hoa, trong khi `source` vẫn giữ bốn tên ban đầu.
- `reuse-plan` phát hiện việc dùng lại pipeline đã tiêu thụ.
- Các dòng đếm, tính tổng và factory dùng Stream mới cho từng lượt.
- `before-start-change` nhìn thấy thay đổi ở `ArrayList` trước khi terminal bắt đầu; `materialized-result` sau đó đã là dữ liệu kết quả riêng.
- `first-match` và `checked` cho thấy lượt tìm kiếm tuần tự không cần kiểm tra `Bo` sau khi tìm thấy `Mai`.
- `generated` có nguồn sinh giá trị, không cần một Collection đã chứa sẵn các số.
- `result-add` và `editable` phân biệt quyền sửa các dạng danh sách đầu ra.
- `shared-object` minh họa cùng một đối tượng phần tử có thể còn được nguồn và kết quả tham chiếu.
- Hai dòng cuối phân biệt hoàn tất terminal với việc đóng Stream.

## 14. Thực hành có đáp án

### Bài 1 — Pipeline đã có dữ liệu kết quả chưa?

Sau `Stream<String> s = names.stream().filter(name -> name.length() >= 3)`, có thể coi `s` là danh sách đã lọc để gọi `get(0)` không?

**Đáp án:** Không. `s` là một Stream mô tả đường xử lý, không có phương thức `get` của List và chưa tạo danh sách kết quả. Nếu cần dữ liệu giữ lại để truy cập theo chỉ số, dùng một terminal thích hợp như `toList` rồi thao tác trên List đó.

### Bài 2 — Đếm rồi lấy danh sách từ cùng Stream

Có thể gọi `s.count()` rồi `s.toList()` trên cùng `s` không? Nêu hai cách sửa theo nhu cầu.

**Đáp án:** Không được tái sử dụng Stream sau terminal. Có thể tạo Stream mới từ nguồn cho mỗi lượt, hoặc tính danh sách một lần rồi lấy `size` của danh sách nếu cả hai kết quả cần dựa trên cùng dữ liệu đã thu.

### Bài 3 — Lọc có xóa nguồn không?

Nguồn là `[Lan, An, Mai, Bo]`. Pipeline lọc tên dài ít nhất ba ký tự rồi viết hoa trả `[LAN, MAI]`. Nguồn có còn `An` và `Bo` không?

**Đáp án:** Có, nguồn vẫn giữ bốn tên nếu lambda không tự sửa nguồn hoặc đối tượng nguồn. `filter` chỉ chọn các phần tử đi tiếp trong pipeline. Muốn xóa tại chỗ phải chọn một thao tác sửa có hợp đồng phù hợp.

### Bài 4 — Stream có đóng băng dữ liệu lúc tạo không?

Tạo Stream từ `ArrayList` đang chứa `A`, thêm `B` trước terminal, rồi thu danh sách. Vì sao kết quả ví dụ là `[A, B]`?

**Đáp án:** Stream từ nguồn này không tự chép dữ liệu thành bản chụp ở lúc gọi `stream`. Thay đổi xảy ra trước khi lượt xử lý bắt đầu được nguồn JDK phù hợp phản ánh. Không dùng điều này để biện minh việc sửa nguồn trong lúc terminal đang chạy hoặc để suy ra hành vi của mọi nguồn tùy biến.

### Bài 5 — Vì sao không đặt công việc bắt buộc trong peek?

Một pipeline gọi `peek` để ghi nhận mọi phần tử rồi kết thúc bằng `count`. Có được dùng số đếm đúng để chứng minh mọi lần ghi nhận đã chạy không?

**Đáp án:** Không. Cách cài đặt có thể suy ra số lượng mà không duyệt các giai đoạn không ảnh hưởng kết quả. Dùng cơ chế thực hiện hành động tường minh, chẳng hạn vòng lặp hoặc terminal phù hợp, thay vì dựa vào một tác dụng phụ có thể bị bỏ qua khi tối ưu.

### Bài 6 — Supplier nào thật sự tạo lượt xử lý mới?

`Supplier<Stream<String>> factory = () -> names.stream()` khác gì một supplier chỉ trả lại biến `savedStream` đã tạo trước đó?

**Đáp án:** Lambda thứ nhất gọi lại `stream` để tạo lượt mới mỗi lần `get`. Lambda thứ hai có thể trả cùng một Stream đã bị tiêu thụ. Bản thân kiểu Supplier không bảo đảm đối tượng mới; phải xem cách nó tạo kết quả.

### Bài 7 — Kết quả không cho sửa có làm đối tượng bên trong bất biến không?

Một `List<StringBuilder>` được đưa qua `stream().toList()`. Có thể sửa `StringBuilder` lấy từ kết quả không? Nguồn có thấy thay đổi không?

**Đáp án:** Danh sách đầu ra không cho thêm/xóa hay thay vị trí bằng mutator của List, nhưng đối tượng `StringBuilder` vẫn sửa được. Nếu nguồn và đầu ra dùng chung tham chiếu, nguồn cũng nhìn thấy trạng thái mới. Cần phép sao chép đối tượng hoặc kiểu bất biến nếu yêu cầu tách trạng thái.

### Bài 8 — Terminal xong có chắc đã đóng tệp không?

Sau `Files.lines(path).count()`, có được bỏ trách nhiệm đóng Stream vì `count` đã là terminal không?

**Đáp án:** Không. Tiêu thụ pipeline và đóng tài nguyên là hai việc. Stream của `Files.lines` phải được đóng theo hợp đồng, thường bằng `try-with-resources`, kể cả khi terminal đã hoàn thành hoặc gặp lỗi.

## 15. Cách đọc một đoạn mã dùng Collection và Stream

Trước hết tìm nơi dữ liệu được giữ và ai có quyền thay đổi nó. Sau đó đọc Stream như một lượt xử lý gồm nguồn, các giai đoạn trung gian và terminal. Xác định kết quả cần được giữ lại hay chỉ cần một giá trị tổng hợp.

Khi cần dùng lại dữ liệu, giữ Collection hoặc tạo lại Stream từ một nguồn còn dùng được. Khi cần dùng lại một công thức xử lý, giữ hàm dựng pipeline mới. Khi nguồn có tài nguyên, xác định trách nhiệm đóng; khi có đối tượng sửa được, phân biệt bản sao cấu trúc và bản sao trạng thái.

Mô hình chính của bài là: **Collection biểu diễn nhóm dữ liệu; Stream biểu diễn một lượt tính toán trên nguồn; terminal tạo kết quả mà ứng dụng cần.** Hiểu được ba vai trò này giúp tránh coi Stream là một danh sách tạm, tránh chạy lại pipeline đã dùng và lựa chọn đúng nơi lưu kết quả.
