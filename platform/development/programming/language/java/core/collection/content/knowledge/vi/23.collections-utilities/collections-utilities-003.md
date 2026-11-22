# min, max, frequency và disjoint

Nhiều câu hỏi về collection chỉ cần một kết quả nhỏ: phần tử thấp nhất, phần tử cao nhất, số lần một giá trị xuất hiện hoặc hai nhóm có chồng lấp hay không. Không cần sắp xếp cả danh sách hay tự tạo một collection giao nếu chỉ muốn trả lời những câu hỏi ấy.

`Collections.min` và `Collections.max` chọn một phần tử theo thứ tự. `Collections.frequency` đếm phần tử bằng một giá trị theo `equals`. `Collections.disjoint` trả lời liệu hai collection có **không có phần tử chung** hay không.

Điểm dễ sai là xem mọi phương thức đều dùng cùng một nghĩa của “bằng nhau”. Comparator, `equals` và cách xác định thành viên của một collection có thể khác nhau. Bài này tách rõ từng hợp đồng, rồi kiểm chứng bằng Java 17 chạy được.

## 1. Chọn phương thức từ câu hỏi cần trả lời

| Câu hỏi | Phương thức | Kết quả | Có thay thứ tự hoặc sửa collection không? |
| --- | --- | --- | --- |
| Phần tử nhỏ nhất theo một thứ tự là gì? | `min(collection)` hoặc `min(collection, comparator)` | Một phần tử `T` | Không cần sửa |
| Phần tử lớn nhất theo một thứ tự là gì? | `max(collection)` hoặc `max(collection, comparator)` | Một phần tử `T` | Không cần sửa |
| Có bao nhiêu phần tử bằng giá trị đang hỏi? | `frequency(collection, value)` | `int` | Không cần sửa |
| Hai collection có hoàn toàn không chung phần tử không? | `disjoint(left, right)` | `boolean` | Không cần sửa |

Các phương thức nhận `Collection`, không chỉ `List`. List, set và nhiều collection khác có thể là đầu vào hợp lệ. Chúng không đòi collection hỗ trợ `add`, `remove` hay `set`.

Map không là kiểu con của `Collection`. Khi làm việc với map, chọn đúng góc nhìn như `keySet()`, `values()` hoặc `entrySet()` để câu hỏi có ý nghĩa.

Một kết quả nhỏ không có nghĩa công việc luôn hằng số. Để biết phần tử lớn nhất trong một collection chưa có cấu trúc hỗ trợ riêng, thường phải duyệt các phần tử. Phải phân biệt lượng dữ liệu trả về với lượng dữ liệu cần đọc.

## 2. `min` và `max` theo thứ tự tự nhiên

### Không cần sắp xếp đầu vào

Đoạn sau là mã minh họa trong một phương thức có đủ import:

~~~java
List<Integer> values = List.of(9, 2, 7, 2);

int lowest = Collections.min(values);
int highest = Collections.max(values);
~~~

`lowest` là 2 và `highest` là 9. List vẫn có thứ tự `[9, 2, 7, 2]`; hai số 2 vẫn có mặt. Không có bước sort, loại trùng hay thay phần tử trong list.

`min` và `max` trả **phần tử**, không trả chỉ số của nó. Với collection không có truy cập chỉ số, câu hỏi về chỉ số vốn không có ý nghĩa.

### Thứ tự tự nhiên đến từ `Comparable`

Overload không có comparator yêu cầu các phần tử có thứ tự tự nhiên và so sánh được với nhau. Với `Integer`, đó là thứ tự số.

Nếu một lớp nghiệp vụ không triển khai `Comparable`, không nên mong `min` tự đoán rằng phải dùng giá, tuổi hay tên. Hãy cung cấp comparator phù hợp.

Nếu lách generic bằng raw type rồi trộn những kiểu không so sánh được, lời gọi có thể ném `ClassCastException` khi cần so sánh. Generic đúng giúp diễn đạt và kiểm tra ý định ở thời điểm biên dịch. [Thứ tự tự nhiên và Comparable, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Comparable.html).

### Cơ chế duyệt và giữ một ứng viên

Có thể hiểu cách tìm min như sau:

1. Lấy một phần tử làm ứng viên ban đầu.
2. Đọc lần lượt các phần tử còn lại.
3. Khi gặp một phần tử nhỏ hơn theo thứ tự đang dùng, thay ứng viên.
4. Sau khi duyệt xong, ứng viên là một phần tử cực tiểu.

Max làm tương tự nhưng giữ ứng viên lớn hơn. Cách này không cần đảo thứ tự các phần tử và không cần tạo một list đã sắp xếp.

Đó cũng là lý do list không sửa được vẫn dùng được với các truy vấn này. Không có quyền sửa vật chứa không đồng nghĩa không được tính toán trên nội dung.

## 3. Comparator quyết định nghĩa của “nhỏ nhất” và “lớn nhất”

### Chọn một trường nghiệp vụ

Giả sử mỗi đề xuất có mã và một con số chi phí:

~~~java
record Offer(String code, int cost) {
}

Comparator<Offer> byCost =
        Comparator.comparingInt(Offer::cost);
~~~

Khi đó:

~~~java
Offer cheapest = Collections.min(offers, byCost);
Offer mostExpensive = Collections.max(offers, byCost);
~~~

Đây là các mảnh mã minh họa với biến `offers` đã tồn tại; chương trình đầy đủ ở dưới khai báo toàn bộ dữ liệu.

Kết quả là một `Offer`, không phải riêng giá trị `cost`. Muốn lấy con số, đọc `cheapest.cost()` sau khi đã chọn phần tử.

Comparator nên mô tả một quan hệ nhất quán và ổn định trong suốt lần duyệt. Không so bằng phép trừ số nguyên có thể tràn; dùng `Integer.compare` hoặc `comparingInt`. Không đổi trường khóa so sánh giữa chừng. [Hợp đồng Comparator, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html).

### Comparator đảo chiều cũng đảo ý nghĩa min/max

Với các số `[9, 2, 7, 2]`:

~~~java
int firstInDescendingOrder =
        Collections.min(values, Comparator.reverseOrder());
~~~

Kết quả là 9. Nó là phần tử “nhỏ nhất” **theo comparator giảm dần**, dù là số lớn nhất theo thứ tự tự nhiên.

Tương tự, `max(values, Comparator.reverseOrder())` trả 2. Đừng đọc tên `min` tách khỏi quy tắc so sánh đã truyền.

Nếu mục tiêu là chọn số lớn nhất tự nhiên, `max(values)` dễ đọc hơn việc dùng `min` với comparator đảo. Comparator đảo hữu ích khi nó là một phần của một quy tắc nghiệp vụ, nhưng tên biến vẫn phải thể hiện đúng ý nghĩa.

### Comparator của một set không tự được dùng

Một `TreeSet` có thể duyệt theo comparator riêng, chẳng hạn giảm dần. Điều đó không đổi hợp đồng của `Collections.min(collection)` thành “lấy phần tử đầu theo comparator của set”.

Với set giảm dần gồm 2, 9, 4:

- `tree.first()` là 9 theo thứ tự mà set duy trì.
- `Collections.min(tree)` là 2 theo thứ tự tự nhiên.
- `Collections.min(tree, tree.comparator())` là 9 theo comparator giảm dần được truyền rõ.

Phân biệt “thứ tự cấu trúc duy trì” và “thứ tự truy vấn chọn dùng”. Nếu muốn dùng quy tắc của set, phải truyền nó hoặc dùng thao tác chuyên biệt có đúng hợp đồng. [Cách TreeSet dùng comparator, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html).

### Nhiều phần tử cùng cực trị

Giả sử A và B đều có `cost` bằng 50. Nếu comparator chỉ so chi phí, cả hai đều là ứng viên hợp lệ cho min.

Hợp đồng chọn phần tử cực trị không nên được diễn giải thành một lời hứa chọn mã cụ thể trong nhóm hòa. Nếu yêu cầu “chi phí nhỏ nhất; khi bằng nhau thì mã nhỏ nhất”, viết tiêu chí phụ:

~~~java
Comparator<Offer> byCostThenCode =
        Comparator.comparingInt(Offer::cost)
                .thenComparing(Offer::code);

Offer selected = Collections.min(offers, byCostThenCode);
~~~

Không dựa vào một lần chạy hiện tại để gán ý nghĩa nghiệp vụ cho thứ tự hòa chưa được quy định. Nếu chỉ quan tâm chi phí min, kiểm thử giá trị chi phí sẽ chính xác hơn việc ép một mã phải thắng khi comparator chưa phân biệt các mã.

## 4. Collection rỗng, `null` và giá trị trả về

### Không có min/max khi không có phần tử

`Collections.min` và `Collections.max` ném `NoSuchElementException` trên collection rỗng. Chúng không trả 0, không tạo một đối tượng mặc định và không dùng `null` như dấu hiệu chung cho “không có phần tử”. [Hợp đồng min/max trong Collections, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#min(java.util.Collection)).

Cách xử lý phụ thuộc API của ứng dụng:

- Nếu không có dữ liệu là trạng thái hợp lệ, kiểm tra và biểu diễn sự vắng mặt rõ ràng.
- Nếu nghiệp vụ bắt buộc có dữ liệu, báo lỗi theo ngữ cảnh.
- Chỉ dùng một giá trị mặc định khi nó thật sự có ý nghĩa, không phải để làm biến mất ngoại lệ.

Ví dụ, số 0 không luôn là min phù hợp của tập dữ liệu vắng: nó có thể bị hiểu nhầm là một quan sát có giá trị 0.

Kiểm tra `isEmpty` rồi đọc dữ liệu cần cùng một trạng thái nguồn ổn định. Nếu bên khác có thể sửa collection giữa hai bước, phép kiểm tra trước không tự tạo một giao dịch.

### `null` chỉ được xếp nếu quy tắc cho phép

Một collection cho chứa `null` chưa có nghĩa thứ tự tự nhiên xử lý `null` khi so sánh. Với dữ liệu có `null`, truyền comparator có chính sách rõ:

~~~java
Comparator<String> nullLast =
        Comparator.nullsLast(Comparator.naturalOrder());

String min = Collections.min(values, nullLast);
String max = Collections.max(values, nullLast);
~~~

Nếu `values` là `["x", null, "x", null]`, min là `"x"` còn max là `null`. `null` đang được xem là lớn hơn các chuỗi không `null`, nên nó có thể là **phần tử kết quả hợp lệ**.

Với `nullsFirst`, hướng ưu tiên `null` đảo lại. Truyền comparator `null` cho overload comparator có nghĩa quay về thứ tự tự nhiên, không có nghĩa bỏ qua phần tử `null`.

Không dùng một collection đặc biệt ít phần tử để suy ra việc so sánh `null` luôn an toàn: có trường hợp thuật toán chưa phải so sánh cặp nào. Chính sách của comparator mới là căn cứ khi cần so sánh.

Nếu mô hình cho phép một min/max thực sự là `null`, đừng gộp kết quả ấy với “collection rỗng”. Một wrapper không biểu diễn được giá trị `null` hiện diện có thể làm mất phân biệt này; thiết kế kết quả phải theo mô hình cụ thể.

### Kết quả không là bản sao phòng vệ

Khi phần tử là đối tượng sửa được, min/max trả một phần tử đã có trong collection, không tự nhân bản nó. Nếu người nhận sửa đối tượng được chọn, collection vẫn giữ tham chiếu tới đối tượng ấy.

Các truy vấn không sửa collection trong quá trình chọn không đồng nghĩa đối tượng kết quả tự có quyền đọc riêng. Cần áp dụng chính sách quyền sở hữu hoặc biểu diễn dữ liệu đã chốt nếu API không muốn lộ đối tượng sống.

## 5. `frequency`: đếm theo `equals`, không theo comparator

### Câu hỏi là “có bao nhiêu phần tử bằng giá trị này?”

~~~java
List<String> labels = Arrays.asList("x", null, "x", null);

int xCount = Collections.frequency(labels, new String("x"));
int nullCount = Collections.frequency(labels, null);
~~~

Cả hai kết quả đều là 2. Đối tượng chuỗi mới vẫn bằng các chuỗi `"x"` theo `equals`; không cần cùng tham chiếu.

Định nghĩa hình thức là đếm các phần tử `e` thỏa `Objects.equals(value, e)`. Khi giá trị đang hỏi là `null`, các phần tử `null` được đếm. Khi không có phần tử phù hợp, kết quả là 0. [API frequency, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#frequency(java.util.Collection,java.lang.Object)), [Objects.equals](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html#equals(java.lang.Object,java.lang.Object)).

Collection rỗng cũng trả 0. Ngược lại, truyền chính collection là `null` không phải một collection rỗng và sẽ gây `NullPointerException`.

### Không có overload comparator

Với `Offer("A", 50)` và `Offer("B", 50)`, comparator theo cost trả 0, nhưng hai record không bằng nhau theo mọi thành phần.

Nếu list có hai đề xuất ấy:

- Đếm một `new Offer("A", 50)` có thể cho 1.
- Đếm một `new Offer("X", 50)` cho 0 dù chi phí cũng là 50.
- Muốn đếm mọi đề xuất có cost 50, cần điều kiện kiểm tra trường hoặc một bước ánh xạ phù hợp.

Một vòng lặp thể hiện rõ ý định:

~~~java
int matchingCost = 0;
for (Offer offer : offers) {
    if (offer.cost() == 50) {
        matchingCost++;
    }
}
~~~

Không cố truyền comparator cho `frequency`; API không có dạng ấy. Phải chọn giữa “bằng nhau theo mô hình đối tượng” và “khớp một điều kiện nghiệp vụ”.

### Không dùng cách tra cứu của set để thay định nghĩa tần suất

Một `TreeSet<String>` không phân biệt hoa thường có thể giữ `"red"` và trả `true` khi hỏi `contains("RED")`. Tuy vậy, `frequency(set, "RED")` đếm theo `String.equals`, nên không đếm phần tử `"red"` ấy.

Không có mâu thuẫn: hai lời gọi đang dùng hai quy tắc khác nhau. Trong trường hợp một set tuân thủ ngữ nghĩa `equals` thông thường, tần suất của một giá trị là 0 hoặc 1; với các cấu trúc dùng quy tắc khác, hãy trở về đúng hợp đồng của từng thao tác.

`frequency` cũng không đếm chuỗi con. Một list chứa `"Java"` hai lần không làm tần suất của `"Ja"` bằng 2. Nó đếm các phần tử nguyên vẹn bằng đối tượng mục tiêu.

## 6. `disjoint`: `true` nghĩa là không có phần tử chung

### Đọc dấu phủ định đúng chiều

~~~java
List<String> requested = List.of("READ", "WRITE", "READ");
Set<String> blocked = Set.of("DELETE", "WRITE");

boolean noOverlap = Collections.disjoint(requested, blocked);
~~~

Kết quả là `false` vì có phần tử chung `"WRITE"`. Nếu muốn biến diễn đạt “có chồng lấp”, dùng phủ định rõ:

~~~java
boolean overlaps = !Collections.disjoint(requested, blocked);
~~~

Tên biến là một phần quan trọng giúp đọc đúng logic. Đừng đặt tên `hasCommon` rồi gán thẳng kết quả `disjoint` nếu điều đó làm đảo ý nghĩa.

Phần tử lặp không đổi câu trả lời tồn tại: chỉ cần một giá trị chung là đủ để `disjoint` trả `false`. Phương thức không trả số lần chung và không tạo collection giao.

### Rỗng và cùng một đối tượng collection

Với collection hợp lệ và các phần tử truy vấn tương thích:

- Một bên rỗng thì không có phần tử chung, nên kết quả là `true`.
- Cả hai bên rỗng vẫn là `true`.
- Truyền cùng một collection không rỗng ở cả hai phía cho `false`.
- Truyền cùng collection rỗng ở cả hai phía cho `true`.

Một collection không rỗng dĩ nhiên có phần tử chung với chính nó. Không cần tạo bản sao chỉ để gọi phép kiểm tra này.

### Có thể dừng khi tìm được phần tử chung

Ý tưởng truy vấn là đọc phần tử từ một collection và kiểm tra thành viên ở collection kia. Khi tìm được một phần tử chung, đã đủ trả `false`; không cần liệt kê toàn bộ giao.

Không nên dựa vào thứ tự gọi `contains` hoặc mặc định phía trái luôn là phía được duyệt. Cách triển khai được quyền chọn một trong hai phía hoặc một cách tính tương đương.

Điều này cũng ảnh hưởng thiết kế các collection có hạn chế loại phần tử hoặc quy tắc so khớp đặc biệt, như phần tiếp theo.

## 7. Điều kiện tương thích của `disjoint`

### Các phần tử cần là đầu vào truy vấn hợp lệ cho cả hai phía

Một collection có `null` và collection kia không cho `null` có thể gây `NullPointerException` tùy thao tác tra cứu được thực hiện. Kiểu phần tử không hợp lệ với collection kia cũng có thể dẫn đến `ClassCastException`.

Vì vậy, không suy rằng “hai generic khác nhau không thể chung phần tử nên luôn trả `true`”. Lời gọi có thể đi qua cách tra cứu có giới hạn kiểu cụ thể.

Tương tự, `disjoint` không phải bộ lọc tự bỏ `null`. Nếu cần dùng `null` như một phần tử chung, hai đầu vào phải hỗ trợ việc truy vấn ấy. Chương trình dùng list cho `null` và `HashSet` cho `null` để thí nghiệm có điều kiện hợp lệ.

`Collection` cho phép những khác biệt có quy định về phần tử không hợp lệ và ngoại lệ truy vấn. [Hợp đồng Collection, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html).

### Hai quy tắc bình đẳng khác nhau có thể làm kết quả không được xác định

Tài liệu `disjoint` nêu rõ: nếu một collection dùng phép xác định bằng nhau phi chuẩn, cả hai phải dùng cùng phép xác định ấy, nếu không kết quả của phương thức không được xác định.

Ví dụ cần chú ý:

- `SortedSet` dùng một thứ tự không nhất quán với `equals`, chẳng hạn quy tắc so chuỗi không phân biệt hoa thường.
- Tập khóa từ `IdentityHashMap` dùng định danh tham chiếu thay vì `equals`.

Không viết một kết quả `true`/`false` được cho là bắt buộc khi trộn những ngữ nghĩa không tương thích như vậy. Đổi vị trí hai đối số hoặc thêm một phần tử phụ không phải cách sửa đúng vấn đề.

Có hai hướng hợp lệ: chuẩn hóa dữ liệu sang một quy tắc nghiệp vụ thống nhất, hoặc bảo đảm cả hai cấu trúc thật sự dùng cùng quan hệ tương đương. “Cùng kiểu phần tử là String” chưa chứng minh hai quan hệ so khớp giống nhau.

Chương trình sẽ thử hai `TreeSet` cùng dùng `String.CASE_INSENSITIVE_ORDER`, một bên chứa `"red"` và một bên chứa `"RED"`. Chúng có cùng quy tắc không phân biệt hoa thường, nên `disjoint` cho `false`. Chương trình **không** trộn một set ấy với một set dựa trên `String.equals` rồi đoán kết quả.

Đây là giới hạn hợp đồng được công bố, không phải một tối ưu riêng chỉ cần nhớ ở một phiên bản Java. [API disjoint, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#disjoint(java.util.Collection,java.util.Collection)).

### Muốn danh sách phần tử chung là một câu hỏi khác

Nếu cần biết chính xác những mã nào chồng lấp để hiển thị lỗi, một boolean chưa đủ. Hãy thực hiện phép tìm giao phù hợp với quy tắc bình đẳng và quyền sửa dữ liệu.

Không gọi `retainAll` trực tiếp trên nguồn người khác chỉ để tính giao nếu không được phép sửa nguồn. Nếu dùng cách tính trên bản sao, vẫn phải giữ đúng ngữ nghĩa phần tử và xem việc lặp có cần giữ hay không.

## 8. Áp dụng cho map qua đúng góc nhìn

Giả sử:

~~~java
Map<String, Integer> quantities =
        Map.of("small", 4, "large", 9, "medium", 4);
~~~

Map không tự là đầu vào của các phương thức nhận `Collection`. Các góc nhìn trả lời những câu hỏi khác nhau:

| Góc nhìn | Ví dụ câu hỏi |
| --- | --- |
| `quantities.keySet()` | Các mã có chồng lấp với một nhóm mã khác không? |
| `quantities.values()` | Số lượng lớn nhất là bao nhiêu? Có bao nhiêu ánh xạ có giá trị 4? |
| `quantities.entrySet()` | Ánh xạ nào có giá trị lớn nhất theo comparator của entry? |

`Collections.max(quantities.values())` trả 9. `frequency(quantities.values(), 4)` trả 2, vì hai ánh xạ có cùng giá trị vẫn đóng góp hai phần tử trong góc nhìn giá trị.

Nếu cần trả cả khóa chiến thắng, chỉ lấy max của `values` rồi quét tìm khóa có thể chưa diễn đạt quy tắc hòa. Có thể chọn entry bằng comparator theo giá trị và thêm tiêu chí khóa nếu cần.

Các góc nhìn của map có thể gắn với nguồn. Chọn xong một entry cũng cần xét hợp đồng vòng đời của entry nếu định giữ nó lâu; không suy rằng một truy vấn đọc đã tự tạo bản snapshot độc lập. [Các collection view của Map, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html).

## 9. Chương trình hoàn chỉnh với stdout chính xác

Lưu mã vào **`CollectionQueriesDemo.java`**. Dữ liệu số và đề xuất được giữ trong list không sửa được để chứng minh các truy vấn không cần quyền cập nhật vật chứa.

Với hai đề xuất cùng chi phí thấp nhất, chương trình chỉ khẳng định giá trị chi phí ở phép chọn chưa có tiêu chí phụ. Phép chọn mã cụ thể chỉ xuất hiện sau khi bổ sung tiêu chí mã vào comparator.

~~~java
import java.util.Arrays;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.NoSuchElementException;
import java.util.Set;
import java.util.TreeSet;

public class CollectionQueriesDemo {
    record Offer(String code, int cost) {
    }

    private static void noElement(String label, Runnable action) {
        try {
            action.run();
            throw new AssertionError(label + " unexpectedly succeeded");
        } catch (NoSuchElementException ex) {
            System.out.println(label + "=NoSuchElementException");
        }
    }

    public static void main(String[] args) {
        List<Integer> numbers = List.of(9, 2, 7, 2);
        System.out.println("numbers.min=" + Collections.min(numbers));
        System.out.println("numbers.max=" + Collections.max(numbers));
        System.out.println("numbers.minReverse="
                + Collections.min(numbers, Comparator.reverseOrder()));
        System.out.println("numbers.maxReverse="
                + Collections.max(numbers, Comparator.reverseOrder()));
        System.out.println("numbers.after=" + numbers);

        List<Offer> offers = List.of(
                new Offer("B", 50),
                new Offer("A", 50),
                new Offer("C", 80));
        Comparator<Offer> byCost = Comparator.comparingInt(Offer::cost);
        Offer cheapest = Collections.min(offers, byCost);
        System.out.println("offer.minCost=" + cheapest.cost());
        System.out.println("offer.maxCode="
                + Collections.max(offers, byCost).code());
        System.out.println("offer.minWithTieBreak="
                + Collections.min(
                        offers, byCost.thenComparing(Offer::code)).code());
        System.out.println("frequency.offerA="
                + Collections.frequency(offers, new Offer("A", 50)));
        System.out.println("frequency.offerX="
                + Collections.frequency(offers, new Offer("X", 50)));
        int cost50 = 0;
        for (Offer offer : offers) {
            if (offer.cost() == 50) {
                cost50++;
            }
        }
        System.out.println("predicate.cost50=" + cost50);

        List<String> nullable = Arrays.asList("x", null, "x", null);
        System.out.println("frequency.null="
                + Collections.frequency(nullable, null));
        System.out.println("frequency.newString="
                + Collections.frequency(nullable, new String("x")));
        System.out.println("frequency.missing="
                + Collections.frequency(nullable, "missing"));
        Comparator<String> nullLast =
                Comparator.nullsLast(Comparator.naturalOrder());
        System.out.println("nulls.minLast="
                + Collections.min(nullable, nullLast));
        System.out.println("nulls.maxLast="
                + Collections.max(nullable, nullLast));

        TreeSet<Integer> reverseSet =
                new TreeSet<>(Comparator.reverseOrder());
        reverseSet.addAll(List.of(2, 9, 4));
        System.out.println("tree.first=" + reverseSet.first());
        System.out.println("tree.minNatural="
                + Collections.min(reverseSet));
        System.out.println("tree.minOwnComparator="
                + Collections.min(reverseSet, reverseSet.comparator()));

        TreeSet<String> insensitive =
                new TreeSet<>(String.CASE_INSENSITIVE_ORDER);
        insensitive.add("red");
        TreeSet<String> sameRule =
                new TreeSet<>(String.CASE_INSENSITIVE_ORDER);
        sameRule.add("RED");
        System.out.println("case.containsRED="
                + insensitive.contains("RED"));
        System.out.println("case.frequencyRED="
                + Collections.frequency(insensitive, "RED"));
        System.out.println("case.disjointSameRule="
                + Collections.disjoint(insensitive, sameRule));

        List<String> requested = List.of("READ", "WRITE", "READ");
        Set<String> blocked = Set.of("DELETE", "WRITE");
        System.out.println("disjoint.common="
                + Collections.disjoint(requested, blocked));
        System.out.println("disjoint.separate="
                + Collections.disjoint(requested, Set.of("ARCHIVE")));
        System.out.println("disjoint.empty="
                + Collections.disjoint(
                        Collections.<String>emptyList(), requested));
        System.out.println("disjoint.selfNonempty="
                + Collections.disjoint(requested, requested));
        List<String> empty = Collections.emptyList();
        System.out.println("disjoint.selfEmpty="
                + Collections.disjoint(empty, empty));
        Set<String> containsNull = new HashSet<>();
        containsNull.add(null);
        System.out.println("disjoint.commonNull="
                + Collections.disjoint(nullable, containsNull));

        Map<String, Integer> quantities =
                Map.of("small", 4, "large", 9, "medium", 4);
        System.out.println("map.maxValue="
                + Collections.max(quantities.values()));
        System.out.println("map.frequency4="
                + Collections.frequency(quantities.values(), 4));
        System.out.println("map.keysDisjoint="
                + Collections.disjoint(
                        quantities.keySet(), Set.of("unknown")));

        noElement("empty.min",
                () -> Collections.min(Collections.<Integer>emptyList()));
        noElement("empty.max",
                () -> Collections.max(Collections.<Integer>emptyList()));
        System.out.println("empty.frequency="
                + Collections.frequency(empty, "x"));
        List<Integer> single = List.of(5);
        System.out.println("single.minMax="
                + Collections.min(single) + "/" + Collections.max(single));
    }
}
~~~

Biên dịch và chạy trong thư mục chứa tệp:

~~~shell
javac --release 17 -encoding UTF-8 CollectionQueriesDemo.java
java CollectionQueriesDemo
~~~

Cần JDK 17 trở lên cho lệnh biên dịch này. Mã đã được biên dịch với `--release 17` và chạy trên OpenJDK 24.0.2, thoát thành công. Stdout chính xác:

~~~text
numbers.min=2
numbers.max=9
numbers.minReverse=9
numbers.maxReverse=2
numbers.after=[9, 2, 7, 2]
offer.minCost=50
offer.maxCode=C
offer.minWithTieBreak=A
frequency.offerA=1
frequency.offerX=0
predicate.cost50=2
frequency.null=2
frequency.newString=2
frequency.missing=0
nulls.minLast=x
nulls.maxLast=null
tree.first=9
tree.minNatural=2
tree.minOwnComparator=9
case.containsRED=true
case.frequencyRED=0
case.disjointSameRule=false
disjoint.common=false
disjoint.separate=true
disjoint.empty=true
disjoint.selfNonempty=false
disjoint.selfEmpty=true
disjoint.commonNull=false
map.maxValue=9
map.frequency4=2
map.keysDisjoint=true
empty.min=NoSuchElementException
empty.max=NoSuchElementException
empty.frequency=0
single.minMax=5/5
~~~

### Giải thích kết quả theo từng quan hệ so khớp

**`numbers`:** min tự nhiên là 2, max tự nhiên là 9. Comparator đảo khiến min là 9 và max là 2. List vẫn có thứ tự gốc; không cần sort để chọn cực trị.

**`offer`:** chi phí thấp nhất là 50; mã của đề xuất cao nhất là C vì chi phí 80 là duy nhất. Khi thêm tiêu chí mã để phá hòa ở chi phí thấp nhất, A được chọn.

**`frequency.offerA`, `frequency.offerX` và `predicate.cost50`:** record A/50 xuất hiện một lần; record X/50 không xuất hiện. Tuy vậy có hai đề xuất cùng chi phí 50. Một điều kiện trên cost không giống phép `equals` của toàn record.

**`frequency.null` và `frequency.newString`:** target `null` được xử lý có nghĩa; một chuỗi mới khác tham chiếu vẫn bằng `"x"` và được đếm hai lần.

**`nulls`:** comparator xếp `null` cuối làm max trả `null` trên collection không rỗng. Đây không phải trường hợp không có kết quả do dữ liệu rỗng.

**`tree`:** phần tử đầu theo thứ tự giảm của set là 9; min tự nhiên vẫn là 2; min được truyền comparator riêng của set là 9.

**`case`:** `contains("RED")` dùng quy tắc set và trả `true`, còn `frequency` dùng `String.equals` nên trả 0. Hai set trong phép `disjoint` dùng cùng quy tắc không phân biệt hoa thường, vì vậy chúng có chung thành viên theo quy tắc ấy.

**`disjoint`:** có WRITE chung cho kết quả `false`; nhóm ARCHIVE riêng cho `true`. Các biên rỗng/cùng đối tượng được thử riêng. Hai collection hỗ trợ `null` nhận ra `null` là một phần tử chung.

**`map`:** max trên giá trị là 9 và có hai giá trị 4. Kiểm tra mã `unknown` trên tập khóa không tìm thấy phần tử chung.

**`empty` và `single`:** min/max không có phần tử để trả nên ném đúng `NoSuchElementException`. Tần suất trên list rỗng bằng 0. Với một phần tử số 5, cả min và max đều là 5.

Hàm `noElement` khiến chương trình thất bại nếu một truy vấn rỗng bất ngờ không ném ngoại lệ. Chương trình không dựa vào nội dung thông báo ngoại lệ hoặc thứ tự duyệt của hash set/map để tạo stdout.

## 10. Chi phí và lựa chọn cho truy vấn lặp lại

### Min/max duyệt thay vì sort

Min hoặc max trên collection thông thường cần một lượt duyệt và giữ một ứng viên. Khi phép so sánh có chi phí hằng và việc duyệt bình thường tuyến tính, công việc là `O(n)` với lượng trạng thái phụ nhỏ.

Sort chỉ để lấy một cực trị thường làm nhiều việc hơn và có thể còn thay thứ tự đầu vào nếu sort trực tiếp. Chỉ sort khi bạn thật sự cần cả thứ tự đã sắp xếp hoặc một bước sau sử dụng nó.

Gọi min rồi max là hai lượt duyệt; tổng vẫn là `O(n)` theo bậc tăng trưởng, không thành `O(n²)`. Nếu cần đồng thời nhiều thống kê trên nguồn đắt tiền, cân nhắc một lượt tổng hợp phù hợp thay vì lặp lại mọi truy vấn.

Với cấu trúc đã có thứ tự và tiêu chí truy vấn trùng thứ tự nó duy trì, các thao tác chuyên biệt như đầu/cuối có thể phù hợp hơn. Phải giữ đúng ý nghĩa comparator; không mặc định `first` của set giảm là số nhỏ nhất tự nhiên.

### Frequency đơn giản cho vài câu hỏi, bảng đếm cho nhiều câu hỏi

Mỗi lần gọi `frequency` phải xét các phần tử theo quy tắc bình đẳng của nó. Nếu hỏi `q` giá trị trên list có `n` phần tử bằng cách gọi riêng từng lần, có thể phải thực hiện công việc cỡ `q × n` phép xét.

Nếu cần thống kê mọi giá trị hoặc tra tần suất nhiều lần, có thể xây dựng bảng đếm một lần:

~~~java
Map<String, Integer> counts = new HashMap<>();
for (String value : values) {
    counts.merge(value, 1, Integer::sum);
}
~~~

Đây là mã minh họa với `List<String> values` và đủ import. Cần giữ hợp đồng `equals`/`hashCode` đúng và biết chính sách `null` của map dùng làm chỉ mục.

`HashMap` hỗ trợ khóa `null` và có chi phí get/put hằng theo điều kiện phân tán mã băm phù hợp. Đó không phải bảo đảm cho mọi cách cài `Map` hoặc cho một hàm `equals` tự viết rất tốn kém. [HashMap, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html).

Bảng đếm cũng cần được cập nhật hoặc dựng lại nếu nguồn thay đổi. Tối ưu truy vấn không được đánh đổi lấy một kết quả đã cũ mà người gọi tưởng còn hiện hành.

### Disjoint phụ thuộc chi phí kiểm tra thành viên

Nếu kiểm tra thành viên ở một list phải quét tuyến tính, so hai list không có phần tử chung có thể cần công việc cỡ tích hai kích thước. Nếu một phía là `HashSet` có tra cứu hiệu quả, phép kiểm tra thường rẻ hơn.

Dựng một hash set riêng có thể có lợi cho nhiều truy vấn, nhưng nó tốn thêm bộ nhớ và phải giữ cùng quan hệ bình đẳng với bài toán. Đừng chuyển một tập theo định danh hay comparator đặc biệt sang `HashSet` rồi nghĩ rằng chỉ có hiệu năng thay đổi.

`HashSet` công bố điều kiện chi phí cho thao tác thành viên dựa trên phân tán mã băm, đồng thời không bảo đảm thứ tự duyệt. [HashSet, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashSet.html).

Không có một công thức `O(n + m)` vô điều kiện cho mọi cặp `Collection` tùy chỉnh. Phải xét cách duyệt, phép `contains`, `equals` và dữ liệu đầu vào thực tế.

## 11. Lỗi thường gặp khi ghép các truy vấn

### Dùng min/max như thể trả một con số mặc định trên rỗng

Collection rỗng không có phần tử cực trị. Giá trị mặc định phải là quyết định của API ứng dụng; min/max không tự tạo quyết định ấy.

### Chọn phần tử theo comparator rồi đếm bằng `frequency` để đếm mọi phần tử hòa

Một min theo cost có thể là A/50. `frequency(offers, selected)` đếm những record bằng A/50, không đếm mọi record có cost 50. Muốn số ứng viên hòa, kiểm tra `comparator.compare(element, selected) == 0` với comparator hợp lệ hoặc kiểm tra đúng trường cần thiết.

### Hiểu `disjoint` là “có giao”

Tên hàm mang ý nghĩa không chung phần tử. `true` là không chồng lấp; `false` là có ít nhất một phần tử chung. Viết tên biến hoặc phủ định rõ để tránh đảo nhánh.

### Đếm trong set rồi dùng kết quả để suy số lần trong nguồn list

Chuyển list thành set có thể làm mất số lần lặp theo quan hệ của set. `frequency(set, x)` không khôi phục được số lần x trong list ban đầu. Muốn tần suất, đếm trên nguồn còn giữ số lần xuất hiện hoặc dùng bảng đếm được xây từ nguồn ấy.

### Tưởng truy vấn chỉ đọc là ảnh chụp nguyên tử

Min/max/frequency/disjoint không chủ động sửa đầu vào, nhưng nhiều lần đọc không tự diễn ra ở cùng một trạng thái nếu nguồn bị cập nhật đồng thời.

Một kết quả “không có mã trùng” ở thời điểm kiểm tra không tự bảo đảm ngay sau đó việc thêm mã sẽ không xung đột với một cập nhật khác. Nếu việc kiểm tra và hành động phải thống nhất, cần một giao thức phù hợp với nơi sở hữu dữ liệu.

Không lấy việc không thấy `ConcurrentModificationException` làm bằng chứng nguồn không đổi. Hợp đồng đồng thời của collection và cách công bố dữ liệu vẫn cần được tôn trọng.

### Tưởng phương thức chọn phần tử là bản sao sâu

Kết quả min/max có thể là cùng đối tượng mà nguồn đang chứa. Nếu cần trả dữ liệu chỉ đọc ổn định ra ngoài, chuyển sang biểu diễn đã chốt hoặc bảo vệ đối tượng theo hợp đồng của ứng dụng.

## 12. Thực hành có đáp án

### Bài 1 — Duyệt hay sắp xếp?

Một list không sửa được chứa `[6, 1, 4, 1]`. Cần biết min và max nhưng giữ nguyên thứ tự list.

**Câu hỏi:** Có cần tạo `ArrayList` rồi sort không? Hai kết quả là gì?

**Đáp án:** Không cần. `Collections.min` trả 1 và `Collections.max` trả 6 mà không sửa thứ tự. Hai số 1 vẫn tồn tại. Chỉ tạo bản sắp xếp nếu cần dùng cả thứ tự ấy cho mục đích khác.

### Bài 2 — Min theo thứ tự giảm

Với `[3, 8, 5]`, gọi `Collections.min(values, Comparator.reverseOrder())`.

**Câu hỏi:** Kết quả là 3 hay 8? Vì sao tên min không tự quyết định thứ tự tự nhiên?

**Đáp án:** Kết quả là 8. Trong thứ tự giảm do comparator quy định, 8 đứng trước 5 và 3, nên là cực tiểu theo chính thứ tự ấy. Muốn min tự nhiên, dùng overload không comparator hoặc comparator tự nhiên.

### Bài 3 — Hai đề xuất cùng chi phí

Có `Offer("B", 20)` và `Offer("A", 20)`. Comparator hiện tại chỉ so cost.

**Câu hỏi:** Nếu kiểm thử bắt buộc A được chọn thì đã đủ hợp đồng chưa? Làm gì nếu yêu cầu thật sự là cost thấp nhất rồi mã nhỏ nhất?

**Đáp án:** Chưa đủ: comparator hiện tại coi cả hai hòa và yêu cầu mã A không được diễn đạt. Dùng `Comparator.comparingInt(Offer::cost).thenComparing(Offer::code)` rồi lấy min. Nếu chỉ quan tâm chi phí, kiểm tra cost bằng 20 thay vì ép một mã.

### Bài 4 — Đếm theo đối tượng hay theo trường?

List có A/20, B/20 và A/20, dùng record `Offer` như chương trình.

**Câu hỏi:** Tần suất của `new Offer("A", 20)` là bao nhiêu? Của `new Offer("X", 20)` là bao nhiêu? Có bao nhiêu phần tử cost 20?

**Đáp án:** Lần lượt là 2, 0 và 3. Hai câu đầu dùng `equals` của toàn record; câu cuối dùng điều kiện trên trường cost. Comparator chỉ so cost không làm record X/20 bằng record A/20.

### Bài 5 — `null` là kết quả hay không có dữ liệu?

List không rỗng chứa `["a", null, "b"]`. Dùng `Comparator.nullsLast(Comparator.naturalOrder())` để lấy max.

**Câu hỏi:** Max là gì? Có được coi đó là bằng chứng list rỗng không?

**Đáp án:** Max là `null` vì comparator đặt `null` lớn hơn mọi chuỗi không `null`. Collection không rỗng. Trên collection rỗng, min/max ném `NoSuchElementException`; không được gộp hai trường hợp nếu mô hình cho phép `null`.

### Bài 6 — Đọc boolean của `disjoint`

A là `["x", "x", "y"]`. B là `["z", "y"]`. C là collection rỗng.

**Câu hỏi:** `disjoint(A, B)`, `disjoint(A, C)` và `disjoint(A, A)` trả gì với các collection dùng `equals` thông thường và phần tử tương thích?

**Đáp án:** Lần lượt là `false`, `true` và `false`. Có y chung giữa A/B; collection rỗng không chung phần tử với A; A không rỗng nên chung phần tử với chính nó. Số lần x lặp không đổi câu trả lời tồn tại này.

### Bài 7 — Set không phân biệt hoa thường

Một `TreeSet` dùng `String.CASE_INSENSITIVE_ORDER` giữ `"red"`. `contains("RED")` trả `true`.

**Câu hỏi:** Có được suy `frequency(set, "RED") == 1` không? Có nên trộn set ấy với một hash set dùng `String.equals` trong `disjoint` rồi bắt buộc một kết quả boolean cụ thể không?

**Đáp án:** Không cho cả hai suy luận. Frequency dùng `Objects.equals` nên không đếm `"red"` là `"RED"`. Disjoint yêu cầu các phép bình đẳng phi chuẩn phải tương thích ở cả hai collection; trộn các quan hệ ấy làm kết quả không được xác định theo hợp đồng. Chuẩn hóa dữ liệu hoặc dùng cùng một quy tắc thực sự ở cả hai phía.

### Bài 8 — Tần suất nhiều lần và dữ liệu còn thay đổi

Một nguồn có n phần tử, cần trả tần suất cho q mã. Mỗi mã đang gọi `Collections.frequency` riêng.

**Câu hỏi:** Công việc có thể tăng theo đại lượng nào? Có thể cải thiện thế nào và cần giữ điều kiện gì?

**Đáp án:** Có thể phải xét cỡ `q × n` phần tử. Xây bảng đếm từ một lượt duyệt rồi tra theo mã có thể phù hợp cho nhiều truy vấn. Phải giữ đúng `equals`/`hashCode`, chính sách `null`, giới hạn bộ nhớ và sự nhất quán khi nguồn thay đổi. Một bảng đếm không được cập nhật là dữ liệu cũ; nó không còn tự đại diện cho trạng thái nguồn hiện tại.

Khi chọn các tiện ích này, hãy xác định quan hệ đang dùng trước: thứ tự để chọn cực trị, `equals` để đếm hay ngữ nghĩa thành viên tương thích để xét chồng lấp. Sau đó xử lý rõ rỗng, `null` và vòng đời của nguồn; kết quả nhỏ mới phản ánh đúng câu hỏi nghiệp vụ.
