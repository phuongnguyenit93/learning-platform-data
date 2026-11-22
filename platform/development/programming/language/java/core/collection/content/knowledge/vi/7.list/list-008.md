# equals và hashCode phụ thuộc thứ tự của List

Một `List` biểu diễn **một dãy**. Vì vậy, khi hỏi hai danh sách có bằng nhau không, Java xét cả phần tử và vị trí của chúng, không chỉ hỏi “có cùng những giá trị nào?”.

Ví dụ:

~~~text
[A, B] và [A, B] -> có thể equals, dù là hai đối tượng List khác nhau
[A, B] và [B, A] -> không equals
[A, A, B] và [A, B] -> không equals
~~~

`hashCode` của List cũng kết hợp hash của các phần tử theo thứ tự. Nhưng “phụ thuộc thứ tự” không có nghĩa mọi dãy khác nhau luôn có hash khác nhau. Hash là một giá trị `int` có thể va chạm; nó không thay thế phép `equals`.

Hiểu hai hợp đồng này đặc biệt cần thiết khi kiểm thử, loại các dãy trùng, dùng List trong HashSet hoặc dùng List làm khóa của HashMap.

## 1. Ba mức so sánh khác nhau

| Cách so sánh | Câu hỏi được trả lời |
| --- | --- |
| `left == right` | Hai biến có trỏ đến cùng đối tượng không? |
| `left.equals(right)` | Hai danh sách có cùng dãy phần tử theo hợp đồng List không? |
| `left.hashCode() == right.hashCode()` | Hai giá trị băm có bằng nhau không? Không đủ để kết luận hai List bằng nhau. |

Ví dụ:

~~~java
// Đoạn mã trong một phương thức; cần các import java.util tương ứng.
List<String> first = new ArrayList<>(List.of("A", "B"));
List<String> second = new LinkedList<>(List.of("A", "B"));

System.out.println(first == second);      // false
System.out.println(first.equals(second)); // true
~~~

Hai đối tượng có cách lưu khác nhau nhưng cùng là List, cùng size và cùng giá trị ở từng vị trí.

Không cần biến LinkedList thành ArrayList mới so sánh được về nội dung dãy. Hợp đồng List được thiết kế để các triển khai tuân thủ có thể so sánh theo cùng một ý nghĩa.

Ngược lại, chỉ nhìn hai biến có cùng kiểu khai báo `List<String>` cũng không chứng minh chúng bằng nhau. Cần kiểm tra dữ liệu.

## 2. Hợp đồng equals: cùng loại tập hợp dãy, cùng size, cùng từng vị trí

Về nội dung, hai List bằng nhau khi:

1. Đối tượng được so sánh cũng là một List.
2. Hai List có cùng số phần tử.
3. Các cặp phần tử tương ứng, từ đầu đến cuối, bằng nhau theo `equals`, có xử lý `null`.

Có thể hình dung:

~~~text
left[0]  tương ứng right[0]
left[1]  tương ứng right[1]
...
left[n-1] tương ứng right[n-1]
~~~

Phép so sánh phần tử có ý nghĩa tương tự `Objects.equals(leftElement, rightElement)`.

Các quy tắc equals và công thức hash có thứ tự được quy định trong [List API của Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#equals(java.lang.Object)).

### Thứ tự có ý nghĩa

~~~java
List<String> first = List.of("A", "B");
List<String> reversed = List.of("B", "A");

System.out.println(first.equals(reversed)); // false
~~~

Ở chỉ số `0`, A không bằng B. Việc hai dãy có cùng size và cùng các giá trị phân biệt không làm chúng bằng nhau.

Nếu hoán đổi hai lần xuất hiện có giá trị bằng nhau, dãy quan sát được có thể vẫn bằng nhau. “Xét thứ tự” không có nghĩa mọi thao tác đổi chỗ nội bộ đều tạo một dãy khác theo equals.

### Số lần xuất hiện cũng có ý nghĩa

~~~java
List<String> first = List.of("A", "A", "B");
List<String> second = List.of("A", "B", "B");

System.out.println(first.equals(second)); // false
~~~

Hai dãy đều có A và B, đều size `3`, nhưng khác tại vị trí `1`.

Không bỏ qua phần tử lặp khi đánh giá bằng nhau của List. Đây là khác biệt quan trọng với việc chuyển dữ liệu thành một Set.

## 3. Equals giữa các triển khai và khả năng chỉnh sửa

Cùng dãy nội dung có thể bằng nhau giữa:

- ArrayList.
- LinkedList.
- Danh sách từ Arrays.asList.
- Danh sách không cho sửa từ List.of hoặc List.copyOf.
- Một view List có cùng nội dung hiện tại.

Ví dụ:

~~~java
List<String> mutable = new ArrayList<>(List.of("A", "B"));
List<String> unmodifiable = List.of("A", "B");

System.out.println(mutable.equals(unmodifiable)); // true
~~~

Khả năng thêm, xóa hay thay phần tử không phải một thành phần trong hợp đồng equals của List. Capacity của một ArrayList cũng không phải một phần của giá trị dãy.

Không đồng nhất “bằng nhau” với:

- Cùng lớp runtime.
- Cùng sức chứa.
- Cùng khả năng chỉnh sửa.
- Cùng cách quản lý bộ nhớ.
- Cùng đối tượng.

Những đặc tính đó có thể quan trọng với một yêu cầu khác, nhưng không được đưa vào kết luận List.equals nếu không phải hợp đồng đã chọn.

### List không bằng Set chỉ vì cùng phần tử

~~~java
List<String> sequence = List.of("A", "B");
Set<String> members = Set.of("A", "B");

System.out.println(sequence.equals(members)); // false
~~~

List so sánh một dãy với một List khác. Set có một hợp đồng giá trị khác. Không dùng một Collection bất kỳ làm đối tượng thay thế cho List trong phép so sánh theo dãy.

## 4. Null và kiểu của phần tử

### Null được so sánh theo vị trí

Nếu nguồn cho phép null:

~~~java
List<String> first = Arrays.asList("A", null, "B");
List<String> second = new ArrayList<>(first);
List<String> moved = Arrays.asList(null, "A", "B");

System.out.println(first.equals(second)); // true
System.out.println(first.equals(moved));  // false
~~~

Hai phần tử null ở cùng vị trí được coi là bằng nhau. Null ở vị trí khác có thể làm dãy khác.

Không dùng List.of để tạo một danh sách có null, vì chính factory đó từ chối null trước khi đến bước so sánh.

### Nội dung hiển thị giống nhau chưa đủ

~~~java
List<Integer> integers = List.of(1);
List<Long> longs = List.of(1L);

System.out.println(integers);             // [1]
System.out.println(longs);                // [1]
System.out.println(integers.equals(longs)); // false
~~~

Integer `1` và Long `1L` không bằng nhau theo equals của các kiểu wrapper đó.

Mặt khác, khác kiểu generic khai báo không tự làm hai danh sách khác nhau. Ví dụ một `List<Object>` và một `List<String>` thực sự chứa các String bằng nhau theo từng vị trí có thể bằng nhau. Equals nhận Object và xét nội dung runtime theo hợp đồng, không quyết định bằng tên tham số generic đã viết trong mã.

### Cùng nội dung khác tham chiếu của phần tử

Hai đối tượng String khác tham chiếu nhưng cùng nội dung có thể equals. Vì List dùng equals của phần tử, nó không đòi mọi cặp phần tử phải là cùng đối tượng.

Nếu một lớp phần tử không cung cấp ý nghĩa equals theo giá trị mà vẫn dùng hành vi mặc định của Object, hai đối tượng riêng biệt có thể không bằng nhau dù trường dữ liệu nhìn giống nhau. List không tự phân tích mọi trường để tạo một định nghĩa equals mới cho phần tử.

## 5. Công thức hashCode của List

List kết hợp hash theo thứ tự bằng phép tích lũy:

~~~java
// Hàm minh họa trong một lớp; cần import java.util.List và java.util.Objects.
static int listHash(List<?> values) {
    int hash = 1;
    for (Object value : values) {
        hash = 31 * hash + Objects.hashCode(value);
    }
    return hash;
}
~~~

`Objects.hashCode(value)` trả `0` nếu value là null; nếu khác null, dùng hashCode của phần tử.

Các điểm cần giữ:

- Giá trị khởi đầu là `1`.
- Mỗi bước nhân kết quả trước đó với `31`.
- Sau đó cộng hash của phần tử hiện tại.
- Duyệt theo đúng thứ tự của List.

Đây là công thức hợp đồng, không phải một thuật toán băm bảo mật. Xem [List.hashCode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#hashCode()).

Với List rỗng, vòng lặp không chạy nên hash là `1`.

### Tính từng bước với A, B

Hash của String `"A"` là `65`, của `"B"` là `66`.

~~~text
[A, B]:

h0 = 1
h1 = 31 * 1  + 65 = 96
h2 = 31 * 96 + 66 = 3042
~~~

Đảo thứ tự:

~~~text
[B, A]:

h0 = 1
h1 = 31 * 1  + 66 = 97
h2 = 31 * 97 + 65 = 3072
~~~

Phần tử ở trước ảnh hưởng tới các lần nhân sau đó, nên phép tích lũy không đơn giản là cộng hash của mọi phần tử theo cách bỏ qua thứ tự.

### Tràn int là một phần của phép tính Java

Hash dùng `int` 32 bit. Với danh sách dài hoặc hash phần tử lớn, phép nhân/cộng có thể vượt miền giá trị có dấu và được tính theo quy tắc số nguyên của Java.

Không tự đổi hàm thành phép cộng kiểm tra tràn rồi ném ngoại lệ, hoặc đổi kết quả sang một kiểu khác mà vẫn gọi đó là cùng công thức List.hashCode.

Giá trị hash có thể âm. Số âm không có nghĩa List hoặc hàm băm bị lỗi.

## 6. Quy tắc bắt buộc và điều không được suy ngược

Với các đối tượng tuân thủ hợp đồng equals/hashCode:

~~~text
left.equals(right) == true
    -> left.hashCode() == right.hashCode()
~~~

Chiều ngược lại không đúng:

~~~text
left.hashCode() == right.hashCode()
    -> chưa thể kết luận left.equals(right)
~~~

Hash khác nhau đủ để biết hai đối tượng không bằng nhau tại trạng thái đang xét, nếu các hợp đồng được tuân thủ. Hash bằng nhau chỉ có nghĩa cần tiếp tục dùng equals để phân biệt.

Không viết:

~~~java
// Sai nếu mục tiêu là quyết định hai List bằng nhau.
boolean same = left.hashCode() == right.hashCode();
~~~

Dùng:

~~~java
boolean same = left.equals(right);
~~~

Nếu left có thể null, có thể dùng `Objects.equals(left, right)` theo ý nghĩa mong muốn.

### Va chạm số đơn giản

~~~text
[1, 0]:
h1 = 31 + 1 = 32
h2 = 31 * 32 + 0 = 992

[0, 31]:
h1 = 31 + 0 = 31
h2 = 31 * 31 + 31 = 992
~~~

Hai List không equals nhưng có cùng hash `992`.

### Khác thứ tự vẫn có thể cùng hash

Hai String `"Aa"` và `"BB"` có cùng hashCode theo công thức của String.

Vì vậy:

~~~text
["Aa", "BB"] và ["BB", "Aa"]
~~~

không bằng nhau theo List.equals, nhưng cùng cho hash `68545`.

Đây không phải List bỏ qua thứ tự. Công thức vẫn xử lý vị trí; các giá trị đầu vào đã có va chạm nên kết quả có thể tiếp tục va chạm.

Nói “hash phụ thuộc thứ tự” cần đi cùng giới hạn “không bảo đảm ánh xạ duy nhất cho mọi dãy”.

## 7. List làm phần tử của HashSet hoặc khóa của HashMap

Hai dãy bằng nhau về giá trị có thể đóng vai trò cùng một khóa:

~~~java
Map<List<String>, String> cache = new HashMap<>();
cache.put(List.of("A", "B"), "cached");

System.out.println(
        cache.get(new LinkedList<>(List.of("A", "B")))
); // cached

System.out.println(cache.get(List.of("B", "A"))); // null
~~~

Lookup không yêu cầu cùng lớp List hoặc cùng tham chiếu với khóa ban đầu.

Trong ví dụ này map không lưu giá trị null, nên null từ lần tra thứ hai có nghĩa không có ánh xạ đó. Với một Map cho phép giá trị null nói chung, cần phân biệt “không có khóa” với “có khóa ánh xạ tới null” bằng API phù hợp khi cần.

Tương tự:

~~~java
Set<List<String>> sequences = new HashSet<>();

sequences.add(new ArrayList<>(List.of("A", "B")));
sequences.add(new LinkedList<>(List.of("A", "B")));
sequences.add(List.of("B", "A"));

System.out.println(sequences.size()); // 2
~~~

HashSet loại hai khóa dãy A, B bằng nhau thành một giá trị tập hợp, còn dãy B, A là một giá trị khác.

Không từ ví dụ suy ra thứ tự duyệt của HashSet sẽ là một trình tự cố định. Bài chỉ kiểm tra số lượng, không in hoặc dựa vào thứ tự các dãy bên trong tập hợp.

## 8. Rủi ro của khóa List có thể thay đổi

Nếu dùng một List có thể sửa làm khóa rồi thay đổi nó, equals hoặc hashCode có thể đổi trong khi cấu trúc băm vẫn đang giữ thông tin từ lúc chèn.

~~~java
// Ví dụ thiết kế có rủi ro, không dùng làm mẫu khóa ổn định.
List<String> key = new ArrayList<>(List.of("A", "B"));
Map<List<String>, String> cache = new HashMap<>();

cache.put(key, "cached");
key.add("C");

// Không dựa vào một kết quả tra cứu cụ thể sau khi sửa khóa như vậy.
~~~

Không có bảo đảm chung để ứng dụng dựa vào hành vi map sau khi một khóa bị thay đổi theo cách ảnh hưởng equals. Xem lưu ý về khóa có thể thay đổi trong [Map API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html).

Không cố sửa bằng cách gọi lại get nhiều lần, hoặc cho rằng map sẽ tự chuyển khóa sang vị trí phù hợp khi nhận ra hash đã đổi. Cần thiết kế dữ liệu khóa ổn định trong thời gian nó thuộc map hoặc set.

### Chụp cấu trúc với các phần tử bất biến

Với các String không null:

~~~java
List<String> input = new ArrayList<>(List.of("A", "B"));
List<String> key = List.copyOf(input);

Map<List<String>, String> cache = new HashMap<>();
cache.put(key, "cached");

input.add("C");

System.out.println(input); // [A, B, C]
System.out.println(key);   // [A, B]
System.out.println(cache.get(List.of("A", "B"))); // cached
~~~

List.copyOf tạo kết quả không cho sửa đổi và không bị những thay đổi cấu trúc tiếp theo của input phản ánh vào nó theo cách một view dùng chung nguồn sẽ làm. Nó có thể tái sử dụng một đối tượng đầu vào phù hợp; không cần và không nên dựa vào danh tính đối tượng của kết quả để kiểm tra tính đúng.

Trong ví dụ này, String bất biến nên cả cấu trúc khóa và dữ liệu ảnh hưởng equals/hash của phần tử đều ổn định. List.copyOf từ chối phần tử null; nếu miền dữ liệu cho phép null, phải chọn chính sách chụp phù hợp thay vì truyền vào rồi giả định mọi dữ liệu đều được chấp nhận.

## 9. Không cho sửa List chưa đủ nếu phần tử vẫn thay đổi

Xét một phần tử có equals/hashCode theo một thuộc tính có thể đổi:

~~~text
List cố định cấu trúc: [label]
label.value ban đầu: "A"
label.value sau đó:   "B"
~~~

Dù không thêm, xóa hay thay phần tử trong List, hash của phần tử đã đổi. Theo công thức List, hash của cả List cũng có thể đổi.

Chương trình đầy đủ bên dưới minh họa:

~~~text
Hash của List trước: 96
Hash của List sau:   97
~~~

List đó được tạo bằng `List.of(label)`, nên không cho sửa cấu trúc. Nhưng đối tượng label bên trong vẫn có thể đổi value.

Phân biệt ba mức:

| Mức | Điều được giữ ổn định |
| --- | --- |
| Chặn add/remove/set qua một List | Chỉ là giới hạn thao tác qua đối tượng hoặc view đó. |
| Chụp cấu trúc List độc lập với một nguồn có thể đổi | Dãy tham chiếu không theo các thay đổi cấu trúc tiếp theo của nguồn. |
| Khóa giá trị thực sự ổn định | Mọi dữ liệu tham gia equals/hashCode của List và phần tử đều ổn định trong thời gian dùng làm khóa. |

Một `Collections.unmodifiableList(backing)` còn có thể phản ánh thay đổi từ backing nếu nơi khác sửa nguồn gốc. Nó không tương đương snapshot.

Ngay cả snapshot nông bằng List.copyOf cũng không tự sao chép sâu một phần tử có thể thay đổi. Với khóa nghiệp vụ, thường nên lưu các giá trị hoặc định danh bất biến đã chọn rõ, thay vì cả một đối tượng nhiều trạng thái.

## 10. equals/hashCode của phần tử là nền móng

Nếu lớp phần tử tự định nghĩa equals theo giá trị, nó cũng cần hashCode tương thích:

~~~text
hai phần tử equals nhau
    -> hash của hai phần tử phải bằng nhau
~~~

Nếu phần tử vi phạm quy tắc đó, hai List có thể bị kéo vào tình trạng bằng nhau nhưng hash khác. List không thể sửa một hợp đồng phần tử sai bằng cách tự hiểu mọi trường hoặc tự suy ra một hàm băm mới.

Các thuộc tính cần có của equals như đối xứng và bắc cầu cũng phải được các phần tử giữ. Ví dụ một lớp equals chỉ so với một lớp khác theo một chiều có thể khiến việc so sánh các container trở nên khó hiểu và sai hợp đồng.

Bài không yêu cầu mọi phần tử tự viết equals. Các kiểu giá trị có sẵn hoặc record có thể phù hợp khi đúng định nghĩa dữ liệu. Điều cần làm là chọn ý nghĩa bằng nhau của phần tử một cách rõ ràng rồi giữ hashCode tương thích.

### Không nhầm với comparator trả 0

Một comparator sắp xếp theo tuổi có thể cho hai người cùng tuổi kết quả `0`, dù equals của người xét ID và coi họ khác nhau.

List.equals không nhận comparator và không tự dùng quy tắc sắp xếp gần nhất. Hai dãy đã sort với các khóa ngang nhau vẫn được so từng phần tử bằng equals.

Vì vậy, việc sort hai danh sách rồi gọi equals chỉ giải quyết một yêu cầu bỏ qua thứ tự khi quy tắc chuẩn hóa được chọn thực sự phù hợp với định nghĩa giá trị cần so sánh. Đừng mặc nhiên cho rằng comparator bằng 0 tương đương equals.

## 11. List lồng nhau và mảng bên trong List

### List lồng nhau xét thứ tự ở mỗi tầng

~~~java
List<List<Integer>> first =
        List.of(List.of(1, 2), List.of(3));

List<List<Integer>> second =
        List.of(List.of(2, 1), List.of(3));

System.out.println(first.equals(second)); // false
~~~

Phần tử đầu của outer List là một inner List. Equals của inner List tiếp tục xét thứ tự `1, 2` so với `2, 1`.

Nếu đổi vị trí hai inner List ở outer List, thứ tự tầng ngoài cũng có ý nghĩa.

Đây là kết quả của việc các phần tử List tự có equals theo dãy, không phải List.equals tự tạo một phép duyệt sâu đặc biệt cho mọi loại đối tượng.

### Mảng dùng equals khác với List

~~~java
int[] first = {1, 2};
int[] second = {1, 2};

System.out.println(
        List.of(first).equals(List.of(second))
); // false

System.out.println(Arrays.equals(first, second)); // true
~~~

Mỗi List ở đây chứa một phần tử kiểu `int[]`. Hai mảng riêng biệt không equals theo nội dung bằng phương thức Object.equals mà mảng thừa hưởng.

Nếu nghiệp vụ muốn phần tử mảng có ngữ nghĩa giá trị, phải chọn cách biểu đạt hoặc wrapper có equals/hashCode theo nội dung phù hợp, hoặc chọn một kiểu dãy giá trị khác. Không chỉ sửa equals mà bỏ qua hashCode của wrapper. Các hàm so sánh mảng được nêu trong [Arrays API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html#equals(int%5B%5D,int%5B%5D)).

Tránh tạo cấu trúc chứa chính nó hoặc chu trình tham chiếu rồi mong equals/hashCode đệ quy theo nội dung luôn có kết quả hữu hạn. Đó không phải một mô hình khóa giá trị List thông thường và có những giới hạn hợp đồng cần xem xét.

## 12. Nếu nghiệp vụ muốn bỏ qua thứ tự

Hãy chọn đúng ý nghĩa thay vì cố diễn giải lại List.equals:

| Nhu cầu | Mô hình so sánh |
| --- | --- |
| Cùng dãy và cùng số lần phần tử ở đúng vị trí | List.equals |
| Cùng tập giá trị phân biệt, bỏ qua số lần lặp | Set.equals với các phần tử tuân thủ hợp đồng |
| Cùng số lần xuất hiện của từng giá trị, bỏ qua thứ tự | So sánh bảng tần suất hoặc một biểu diễn đa tập phù hợp |

Một cách kiểm tra dễ sai:

~~~java
boolean same = left.size() == right.size()
        && left.containsAll(right)
        && right.containsAll(left);
~~~

Với:

~~~text
left  = [A, A, B]
right = [A, B, B]
~~~

size bằng nhau và hai bên đều chứa A, B, nhưng số lần xuất hiện khác. Biểu thức không chứng minh bằng nhau theo dãy, cũng không chứng minh bằng nhau theo đa tập.

Chuyển cả hai thành HashSet rồi so sánh sẽ bỏ thông tin số lần lặp. Đó có thể là điều nghiệp vụ muốn, nhưng phải chủ động chọn, không coi là một cách tối ưu giữ nguyên ý nghĩa List.equals.

Khi kiểm thử một API trả danh sách, xác định hợp đồng có cam kết thứ tự không. Nếu có, so sánh List là phù hợp. Nếu không có, kiểm thử cần thể hiện rõ ý nghĩa tập hoặc đa tập mong muốn, không tùy tiện sort dữ liệu rồi che một lỗi thứ tự mà API thật sự đã cam kết.

## 13. Chương trình hoàn chỉnh

Lưu thành **ListEqualityHashDemo.java**. Lớp MutableLabel được dùng có chủ ý để minh họa hash thay đổi khi phần tử thay trạng thái; chương trình không đưa danh sách chứa MutableLabel vào Map rồi tiếp tục sửa khóa.

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedList;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public class ListEqualityHashDemo {
    public static void main(String[] args) {
        List<String> arrayList = new ArrayList<>(List.of("A", "B"));
        List<String> linkedList = new LinkedList<>(List.of("A", "B"));
        List<String> reversed = List.of("B", "A");

        System.out.println("Same reference = " + (arrayList == linkedList));
        System.out.println("Cross-implementation equals = "
                + arrayList.equals(linkedList));
        System.out.println("Reverse direction equals = "
                + linkedList.equals(arrayList));
        System.out.println("Reordered equals = " + arrayList.equals(reversed));
        System.out.println("AB hash = " + arrayList.hashCode());
        System.out.println("BA hash = " + reversed.hashCode());
        System.out.println("Manual AB hash = " + listHash(arrayList));
        System.out.println("Empty list hash = " + List.of().hashCode());

        List<Integer> collisionLeft = List.of(1, 0);
        List<Integer> collisionRight = List.of(0, 31);
        System.out.println("Collision equals = "
                + collisionLeft.equals(collisionRight));
        System.out.println("Collision hashes = "
                + collisionLeft.hashCode() + ", " + collisionRight.hashCode());

        List<String> swappedCollisionLeft = List.of("Aa", "BB");
        List<String> swappedCollisionRight = List.of("BB", "Aa");
        System.out.println("Reordered collision equals = "
                + swappedCollisionLeft.equals(swappedCollisionRight));
        System.out.println("Reordered collision hashes = "
                + swappedCollisionLeft.hashCode()
                + ", " + swappedCollisionRight.hashCode());

        List<String> withNull = Arrays.asList("A", null, "B");
        List<String> withNullCopy = new ArrayList<>(withNull);
        List<String> nullMoved = Arrays.asList(null, "A", "B");
        System.out.println("Null-aware equals = "
                + withNull.equals(withNullCopy));
        System.out.println("Null moved equals = " + withNull.equals(nullMoved));

        System.out.println("Duplicate count equals = "
                + List.of("A", "A", "B").equals(List.of("A", "B")));
        System.out.println("List versus set equals = "
                + arrayList.equals(Set.of("A", "B")));

        Set<List<String>> sequences = new HashSet<>();
        sequences.add(arrayList);
        sequences.add(linkedList);
        sequences.add(reversed);
        System.out.println("Distinct sequences in HashSet = "
                + sequences.size());

        List<String> mutableInput = new ArrayList<>(List.of("A", "B"));
        List<String> stableKey = List.copyOf(mutableInput);
        Map<List<String>, String> cache = new HashMap<>();
        cache.put(stableKey, "cached");
        mutableInput.add("C");
        System.out.println("Changed input = " + mutableInput);
        System.out.println("Stable key = " + stableKey);
        System.out.println("Equal sequence lookup = "
                + cache.get(new LinkedList<>(List.of("A", "B"))));
        System.out.println("Reordered lookup = "
                + cache.get(List.of("B", "A")));

        MutableLabel label = new MutableLabel("A");
        List<MutableLabel> fixedStructure = List.of(label);
        int before = fixedStructure.hashCode();
        label.rename("B");
        int after = fixedStructure.hashCode();
        System.out.println("Unmodifiable list hash before/after = "
                + before + ", " + after);

        int[] firstArray = {1, 2};
        int[] secondArray = {1, 2};
        System.out.println("Lists of separate arrays equal = "
                + List.of(firstArray).equals(List.of(secondArray)));
        System.out.println("Array contents equal = "
                + Arrays.equals(firstArray, secondArray));

        List<List<Integer>> nested = List.of(List.of(1, 2), List.of(3));
        List<List<Integer>> nestedReordered =
                List.of(List.of(2, 1), List.of(3));
        System.out.println("Nested inner order equals = "
                + nested.equals(nestedReordered));
    }

    private static int listHash(List<?> values) {
        int hash = 1;
        for (Object value : values) {
            hash = 31 * hash + Objects.hashCode(value);
        }
        return hash;
    }

    private static final class MutableLabel {
        private String value;

        private MutableLabel(String value) {
            this.value = Objects.requireNonNull(value);
        }

        private void rename(String newValue) {
            value = Objects.requireNonNull(newValue);
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof MutableLabel label
                    && value.equals(label.value);
        }

        @Override
        public int hashCode() {
            return value.hashCode();
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~shell
javac --release 17 -encoding UTF-8 ListEqualityHashDemo.java
java ListEqualityHashDemo
~~~

Stdout:

~~~text
Same reference = false
Cross-implementation equals = true
Reverse direction equals = true
Reordered equals = false
AB hash = 3042
BA hash = 3072
Manual AB hash = 3042
Empty list hash = 1
Collision equals = false
Collision hashes = 992, 992
Reordered collision equals = false
Reordered collision hashes = 68545, 68545
Null-aware equals = true
Null moved equals = false
Duplicate count equals = false
List versus set equals = false
Distinct sequences in HashSet = 2
Changed input = [A, B, C]
Stable key = [A, B]
Equal sequence lookup = cached
Reordered lookup = null
Unmodifiable list hash before/after = 96, 97
Lists of separate arrays equal = false
Array contents equal = true
Nested inner order equals = false
~~~

## 14. Giải thích bằng chứng

**Cùng dãy, khác triển khai**

Hai List không cùng tham chiếu nhưng equals cả hai chiều. Cách lưu ArrayList hay LinkedList không thay ý nghĩa dãy A, B.

**Đảo thứ tự**

A, B không bằng B, A. Hash lần lượt là `3042` và `3072` trong ví dụ, phù hợp phép tính tích lũy.

**Manual hash và List rỗng**

Hàm listHash tự tính theo từng phần tử cho cùng hash với List. List rỗng không có bước tích lũy nào nên hash là `1`.

**Hai loại va chạm**

Các dãy số khác nhau cho cùng `992`. Hai dãy String khác thứ tự cũng cho cùng `68545` do hash các String Aa và BB trùng nhau. Trong cả hai trường hợp, equals vẫn false.

**Null và số lần xuất hiện**

Null ở đúng vị trí được so sánh nhất quán; chuyển null sang vị trí khác làm dãy khác. Dãy có thêm một A không bằng dãy thiếu lần xuất hiện đó.

**HashSet chứa các dãy**

A, B từ hai triển khai là cùng một giá trị List, còn B, A là giá trị khác. Vì vậy có hai phần tử List trong HashSet.

**Khóa snapshot của String**

Input được thêm C nhưng stableKey vẫn A, B. Một LinkedList khác có cùng dãy tìm được giá trị đã lưu. Dãy đảo không tìm được khóa trong map của chương trình.

**Cấu trúc không cho sửa nhưng hash đổi**

MutableLabel chuyển A thành B, làm hash phần tử đổi từ hash String A sang hash String B. List một phần tử tương ứng đổi `96` thành `97`, dù không có add/remove/set trên List.

**Mảng và List lồng nhau**

Hai mảng khác tham chiếu không tự được List so sánh theo nội dung. Hai inner List lại được so bằng hợp đồng List của chính chúng, nên thứ tự bên trong vẫn có ý nghĩa.

## 15. Kiểm thử và chi phí

Các ca kiểm thử nên có:

1. Hai List cùng nội dung nhưng khác đối tượng và khác triển khai.
2. Hai List khác thứ tự.
3. Phần tử trùng và số lần trùng khác nhau.
4. Null cùng vị trí và null khác vị trí khi nguồn cho phép.
5. List rỗng.
6. Hai List bằng nhau phải có cùng hash.
7. Hai List khác nhau có thể có cùng hash; không viết yêu cầu mọi hash phải khác.
8. Phần tử có equals/hashCode theo giá trị.
9. Phần tử mảng hoặc đối tượng có thể thay đổi.
10. Khóa được chụp để không bị sửa cấu trúc từ nguồn ban đầu.

Đừng kiểm thử hash bằng yêu cầu “đổi thứ tự thì mọi trường hợp hash phải đổi”. Hãy kiểm tra đúng công thức và quan hệ bắt buộc từ equals sang hash.

Về chi phí, so sánh dãy có thể kết thúc sớm khi thấy khác size hoặc một cặp phần tử khác nhau; trường hợp bằng nhau cần kiểm tra đủ dữ liệu liên quan. Chi phí thực tế còn phụ thuộc equals của phần tử và triển khai List.

Tính hash theo công thức thường phải tích lũy qua các phần tử, cùng chi phí hash của từng phần tử. Đừng giả định hashCode là một định danh sẵn có có chi phí hằng số cho mọi List, hoặc cache hash của một cấu trúc có thể thay đổi mà không có cơ chế vô hiệu hóa đúng.

Việc đọc equals/hashCode trên một nguồn đang bị cập nhật đồng thời cũng không tự tạo snapshot hoặc một bảo đảm nhất quán cho cả dãy. Chọn dữ liệu ổn định hoặc giao thức truy cập phù hợp với yêu cầu.

## 16. Lỗi thường gặp

| Hiểu nhầm | Cách hiểu cần giữ |
| --- | --- |
| Cùng phần tử phân biệt là List.equals | List còn xét thứ tự và số lần xuất hiện. |
| Phải cùng lớp ArrayList mới bằng nhau | Các triển khai List tuân thủ so theo cùng hợp đồng dãy. |
| Cùng toString là equals | Phần tử khác kiểu hoặc khác equals có thể hiển thị giống nhau. |
| List.equals so phần tử bằng == | Nó dùng equals theo từng vị trí, có xử lý null. |
| Hash bằng nhau là hai List bằng nhau | Có thể có va chạm; cần equals. |
| Hash phụ thuộc thứ tự nên mọi hoán vị có hash khác | Va chạm phần tử hoặc công thức có thể cho cùng hash. |
| List không cho sửa thì hash chắc chắn bất biến | Phần tử hoặc nguồn phía sau một view vẫn có thể thay đổi. |
| List.copyOf luôn sao chép sâu mọi dữ liệu | Nó không sao chép sâu đối tượng phần tử. |
| Thay khóa trong map thì map tự cập nhật vị trí băm | Phải giữ dữ liệu tham gia equals/hash ổn định khi là khóa. |
| List chứa mảng tự được so sâu theo nội dung mảng | List dùng equals/hash của phần tử; mảng có quy tắc khác. |
| containsAll hai chiều kèm size thay cho List.equals | Không giữ được thứ tự và có thể sai cả số lần lặp. |

## 17. Thực hành

1. Tính tay hash của `List.of(1, 2)` và `List.of(2, 1)`, rồi kiểm tra bằng chương trình.
2. Tạo một ArrayList và một LinkedList có cùng null ở cùng vị trí; kiểm tra equals hai chiều và hash.
3. Dùng các String Aa, BB để tạo hai dãy đảo nhau có hash bằng nhau nhưng không equals.
4. Tạo hai danh sách cùng size và containsAll hai chiều nhưng khác số lần xuất hiện. Giải thích vì sao phép kiểm tra đó không đúng cho đa tập.
5. Thiết kế một khóa ghép dạng List của các giá trị bất biến. Kiểm tra tra cứu bằng một List khác triển khai có cùng dãy.
6. Thay phần tử có thể đổi trạng thái bên trong một List không cho sửa. Quan sát hash trước–sau mà không đưa khóa không ổn định vào một map thực.
7. Chọn mô hình so sánh cho ba yêu cầu: tuyến đường có thứ tự điểm đi qua, tập quyền không trùng, và giỏ hàng cần đếm số lần xuất hiện của từng mã.

Trước khi so sánh hoặc dùng List làm khóa, hãy xác định giá trị đang cần biểu diễn là một dãy, một tập hay một đa tập. Với dãy, equals xét từng vị trí; hashCode tích lũy theo cùng thứ tự và chỉ hỗ trợ tra cứu, không thay thế định nghĩa bằng nhau.
