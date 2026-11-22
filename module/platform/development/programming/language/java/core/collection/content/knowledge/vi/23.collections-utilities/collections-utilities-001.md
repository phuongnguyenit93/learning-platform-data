# sort, reverse và shuffle: ba cách thay đổi thứ tự của List

Một danh sách lưu các phần tử theo vị trí, nhưng “thay đổi thứ tự” có thể phục vụ những mục đích rất khác. Sắp xếp điểm từ thấp đến cao cần một tiêu chí so sánh. Xem lại lịch sử từ cuối lên đầu chỉ cần đảo thứ tự đang có. Trộn thứ tự câu hỏi cần một phép hoán vị ngẫu nhiên.

`Collections.sort`, `Collections.reverse` và `Collections.shuffle` tương ứng với ba mục đích đó. Chúng đều làm việc trên **list được truyền vào**, trả về `void` và không tự tạo bản kết quả riêng. Vì vậy bài học gồm hai câu hỏi song song: thứ tự nào được tạo ra và ai sẽ quan sát thấy sự thay đổi.

Các ví dụ chạy được dùng Java 17. Người học cần biết `List`, `ArrayList`, tham chiếu và ý nghĩa cơ bản của `Comparator`. Bài sẽ giải thích thêm tính ổn định của sort và vai trò của seed khi shuffle.

## 1. Phân biệt mục tiêu trước khi gọi hàm

| Thao tác | Quy tắc tạo thứ tự | Có so sánh giá trị? | Một mục đích điển hình |
| --- | --- | --- | --- |
| `Collections.sort(list)` | Tăng theo thứ tự tự nhiên | Có | Xếp số từ nhỏ đến lớn |
| `Collections.sort(list, comparator)` | Theo comparator | Có | Xếp điểm giảm dần rồi mã tăng dần |
| `Collections.reverse(list)` | Vị trí `i` chuyển tới `n - 1 - i` | Không | Đảo dãy sự kiện hiện có |
| `Collections.shuffle(list)` | Trộn vị trí bằng nguồn ngẫu nhiên mặc định | Không | Trộn dãy cho một lượt thực hành |
| `Collections.shuffle(list, random)` | Trộn vị trí bằng nguồn ngẫu nhiên được chỉ định | Không | Tái hiện một thí nghiệm với seed đã biết |

Cả ba nhóm thao tác giữ nguyên số phần tử và số lần xuất hiện của từng phần tử. Chúng đổi vị trí, không loại trùng, không tạo bản sao sâu và không tự sửa các trường nghiệp vụ bên trong phần tử.

Ví dụ dãy `[4, 1, 3, 1, 2]`:

- Sort tăng tạo `[1, 1, 2, 3, 4]`.
- Reverse dãy ban đầu tạo `[2, 1, 3, 1, 4]`.
- Shuffle tạo một hoán vị, vẫn có hai số 1 và một lần mỗi số 2, 3, 4.

Reverse không tự hiểu “giảm dần”. Shuffle cũng không đồng nghĩa “thứ tự chắc chắn khác lần trước”. Chọn thao tác theo hậu điều kiện thật sự cần có.

## 2. Đổi ngay list đầu vào và giữ quyền sở hữu rõ ràng

### Ba hàm đều trả `void`

Đây là mã minh họa trong một phương thức:

~~~java
List<Integer> values = new ArrayList<>(List.of(3, 1, 2));
Collections.sort(values);
~~~

Sau lời gọi, `values` biểu diễn `[1, 2, 3]`. Không có list mới được trả từ `sort` để gán cho một biến khác. `reverse` và `shuffle` cũng có cách dùng như vậy.

Nếu hai biến cùng trỏ tới list này, cả hai đều nhìn thấy thứ tự mới:

~~~java
List<Integer> alias = values;
Collections.reverse(values);
// alias cũng nhìn thấy [3, 2, 1].
~~~

Đây là tác dụng của cùng một đối tượng list, không phải việc thuật toán tự tìm và sửa mọi biến trong chương trình.

### Tạo bản làm việc khi cần giữ thứ tự gốc

~~~java
List<Integer> original = List.of(3, 1, 2);
List<Integer> working = new ArrayList<>(original);
Collections.sort(working);
~~~

`original` vẫn giữ thứ tự cũ, còn `working` có thứ tự đã sắp xếp. Hàm tạo list sao chép các tham chiếu phần tử; nó không tự nhân bản từng đối tượng.

Với phần tử là đối tượng sửa được, bản làm việc riêng bảo vệ **thứ tự list nguồn**, không tự bảo vệ mọi trạng thái phần tử. Nếu comparator hoặc mã khác sửa chính đối tượng ấy, các list chia sẻ phần tử có thể cùng nhìn thấy thay đổi.

Cần làm rõ hợp đồng phương thức: “sắp xếp list được truyền vào” hay “trả một list đã sắp xếp và giữ nguyên đầu vào”. Không để người gọi phải đoán từ tên một biến cục bộ.

### List cần hỗ trợ thay vị trí, không nhất thiết cần đổi kích thước

Những thao tác này không cần thêm hoặc xóa phần tử để hoàn thành nhiệm vụ, nhưng cần quyền thay các giá trị ở vị trí của list hoặc qua iterator.

Một list do `Arrays.asList(array)` tạo có kích thước cố định nhưng hỗ trợ thay phần tử nên có thể sort, reverse và shuffle. Vì nó dựa trên mảng, thứ tự trong chính mảng cũng thay đổi. [Hợp đồng Arrays.asList, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html#asList(T...)).

List do `List.of` hoặc `List.copyOf` tạo không cho sửa; `Collections.unmodifiableList` cũng không cấp quyền sửa qua view. Nếu cần xử lý thứ tự, tạo bản làm việc sửa được phù hợp. [Các list không sửa được trong Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#unmodifiable).

Không dùng một thao tác không có tác dụng trên list rỗng hay một phần tử để đoán quyền sửa. Một thuật toán có thể không phải gọi bước thay vị trí trong trường hợp ấy; kết quả “không ném lỗi” chưa chứng minh list hỗ trợ xử lý tổng quát.

## 3. `sort`: tạo thứ tự bằng quy tắc so sánh

### Thứ tự tự nhiên

`Collections.sort(list)` dùng thứ tự tự nhiên của các phần tử. Các phần tử phải so sánh được với nhau theo hợp đồng `Comparable` phù hợp.

~~~java
List<Integer> scores = new ArrayList<>(List.of(8, 3, 8, 5));
Collections.sort(scores);
~~~

Kết quả là `[3, 5, 8, 8]`. Hai số 8 vẫn còn; sort không là phép loại trùng.

Dùng generic đúng kiểu giúp tránh đưa các loại không so sánh được vào cùng list. Nếu lách kiểu qua raw type rồi trộn các loại không tương thích, không nên chờ sort tự tìm một quy tắc hợp lý; quá trình so sánh có thể ném `ClassCastException`.

### Comparator mô tả quy tắc cho một lần sắp xếp

Với một đối tượng kết quả thi, có thể muốn sắp xếp theo điểm thay vì thứ tự tự nhiên của chính lớp:

~~~java
Comparator<Attempt> byPoints =
        Comparator.comparingInt(Attempt::points);

Collections.sort(attempts, byPoints);
~~~

Đây là đoạn minh họa với kiểu `Attempt` và biến `attempts` đã tồn tại; chương trình đầy đủ bên dưới khai báo cả hai.

`compare(a, b)` trả số âm khi `a` đứng trước `b`, 0 khi hai phần tử bằng nhau theo tiêu chí sắp xếp, số dương khi `a` đứng sau `b`. Số trả về không phải vị trí đích và cũng không phải một giá trị boolean.

Không dùng phép trừ số nguyên như `a.points() - b.points()` làm cách so sánh tổng quát; phép trừ có thể tràn. `Integer.compare` hoặc `Comparator.comparingInt` biểu đạt việc so sánh mà không dùng phép trừ rủi ro ấy.

### Ghép và đảo tiêu chí đúng tầng

~~~java
Comparator<Attempt> order =
        Comparator.comparingInt(Attempt::points)
                .reversed()
                .thenComparing(Attempt::id);
~~~

Quy tắc trên là điểm giảm dần; khi điểm bằng nhau, mã tăng dần.

Nếu đặt `reversed()` sau toàn bộ `thenComparing`, cả hai tiêu chí đều bị đảo. Điều đó có thể đúng hoặc sai tùy yêu cầu, nhưng hai cách viết không tương đương.

Comparator phải nhất quán: chẳng hạn, nếu `a` đứng sau `b` và `b` đứng sau `c`, quan hệ phải có tính bắc cầu để `a` cũng đứng sau `c`. Không trả kết quả ngẫu nhiên, không thay tiêu chí giữa chừng và không sửa khóa so sánh trong khi sort.

Một comparator vi phạm hợp đồng có thể dẫn đến kết quả không đúng hoặc `IllegalArgumentException` nếu vi phạm được phát hiện. Không dựa vào việc “chạy một lần chưa ném lỗi” để coi comparator là hợp lệ. [Hợp đồng Comparator, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html).

### `List.sort` và `Collections.sort`

Với comparator, có thể viết `list.sort(comparator)`. `Collections.sort` của Java 17 chuyển việc thực hiện sang `List.sort` theo tài liệu triển khai.

Hai cách gọi đều nhằm sắp xếp list hiện có. Việc chọn cú pháp không tạo một bản sao đầu vào và không thay yêu cầu về tính sửa được.

Không biến thuật toán cụ thể thành hợp đồng bất biến của mọi list tùy chỉnh. Bảo đảm quan trọng khi sử dụng là kết quả theo quy tắc so sánh và tính ổn định; các lớp có thể có cách thực hiện riêng đáp ứng hợp đồng. [API List.sort, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#sort(java.util.Comparator)).

## 4. Tính ổn định của sort và bẫy sort rồi reverse

### “Bằng nhau” trong sort là comparator trả 0

Giả sử dữ liệu đầu vào theo đúng thứ tự:

~~~text
B:2, D:1, A:2, C:1
~~~

Ký hiệu là `mã:điểm`. Khi chỉ so theo điểm, B và A được xem là bằng nhau theo tiêu chí; D và C cũng như vậy, dù các đối tượng không bằng nhau về mọi trường.

Sort **ổn định** (stable sort) giữ thứ tự tương đối ban đầu của các phần tử mà comparator xem là bằng nhau.

Sort tăng theo điểm cho:

~~~text
D:1, C:1, B:2, A:2
~~~

D vẫn đứng trước C; B vẫn đứng trước A. `Collections.sort` bảo đảm tính ổn định. [API Collections.sort, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#sort(java.util.List,java.util.Comparator)).

### Đảo toàn dãy cũng đảo thứ tự trong từng nhóm bằng điểm

Reverse kết quả tăng ở trên cho:

~~~text
A:2, B:2, C:1, D:1
~~~

Điểm đã giảm dần, nhưng B/A và D/C đều đổi thứ tự. Nếu yêu cầu là “điểm giảm dần, người có cùng điểm giữ thứ tự tiếp nhận”, sort tăng rồi reverse không đáp ứng.

Cách đúng cho yêu cầu ấy là sort trực tiếp với comparator giảm dần. Tính ổn định của sort giữ thứ tự gốc trong các nhóm bằng điểm:

~~~text
B:2, A:2, D:1, C:1
~~~

Nếu yêu cầu thật sự là “điểm giảm, khi bằng điểm thì mã tăng”, hãy ghi cả tiêu chí mã vào comparator. Khi ấy việc giữ thứ tự tiếp nhận không còn là tiêu chí cho những phần tử khác mã.

### Ổn định không tự tạo một thứ tự đầu vào xác định

Nếu list được xây từ một nguồn không bảo đảm thứ tự duyệt, giữ thứ tự ban đầu trong các nhóm bằng nhau chỉ giữ thứ tự đã quan sát ở lần xây đó. Nó không tự tạo một quy tắc phụ ổn định giữa các lần chạy.

Khi báo cáo cần kết quả xác định, bổ sung tiêu chí phá hòa có ý nghĩa như mã duy nhất. Khi thứ tự tiếp nhận có ý nghĩa, phải lưu giữ chính thứ tự ấy từ đầu.

## 5. `reverse`: ánh xạ vị trí, không so sánh nội dung

Với `n` phần tử, reverse đưa phần tử cũ ở chỉ số `i` tới chỉ số `n - 1 - i`. Có thể hiểu bằng việc đổi chỗ hai đầu rồi tiến dần vào giữa.

~~~text
trước: [a, b, c, d, e]
sau:   [e, d, c, b, a]
~~~

Phần tử giữa của dãy lẻ ở nguyên vị trí. Một dãy rỗng hay chỉ một phần tử vẫn có cùng thứ tự sau đảo. Nếu không có tác động khác ở giữa, reverse hai lần khôi phục thứ tự ban đầu.

Reverse không cần phần tử triển khai `Comparable` và không cần comparator. Nếu list cho phép phần tử `null`, thao tác chỉ đổi vị trí của `null` như các phần tử khác, không so sánh nó.

### Reverse không thay thế sort giảm dần

Với `[4, 1, 3, 1, 2]`, reverse cho `[2, 1, 3, 1, 4]`. Kết quả không tăng cũng không giảm.

Chỉ khi dãy đầu vào đã được sắp tăng theo một tiêu chí thì đảo nó mới cho thứ tự giảm theo tiêu chí đó. Ngay cả khi ấy vẫn phải xét yêu cầu thứ tự tương đối trong nhóm bằng nhau như phần trước.

### Phân biệt các tên gần giống

- `Collections.reverse(list)` sửa thứ tự các vị trí ngay trong list.
- `Collections.reverseOrder()` tạo comparator ngược thứ tự tự nhiên.
- `Collections.reverseOrder(comparator)` hoặc `comparator.reversed()` tạo quy tắc so sánh ngược.

Tạo comparator không làm list nào tự đổi thứ tự. Phải đưa quy tắc ấy cho một thao tác sort hoặc một cấu trúc có sử dụng comparator.

Nếu đang đọc mã phiên bản Java mới có một API view đảo chiều, không đánh đồng nó với `Collections.reverse`. Trọng tâm ở đây là phương thức `void` sửa list đã truyền; chương trình dùng API Java 17.

## 6. `shuffle`: hoán vị các vị trí bằng nguồn ngẫu nhiên

### Cơ chế chọn dần từ cuối

Một cách hiểu thuật toán là đi từ vị trí cuối về đầu. Ở mỗi lượt, chọn ngẫu nhiên một vị trí trong đoạn chưa chốt, bao gồm chính vị trí hiện tại, rồi đổi chỗ.

Mã sau chỉ minh họa cơ chế cho list có quyền sửa; nó không phải chương trình độc lập và không nhằm thay thế lời gọi thư viện:

~~~java
for (int remaining = values.size(); remaining > 1; remaining--) {
    int selected = random.nextInt(remaining);
    Collections.swap(values, remaining - 1, selected);
}
~~~

Ở lượt đầu của dãy dài 4, chọn trong 4 vị trí để chốt cuối dãy; lượt sau chọn trong 3 vị trí còn lại; tiếp tục với 2. Đây là ý tưởng trộn Fisher–Yates.

Việc chọn đúng miền `[0, remaining)` rất quan trọng. Một vòng lặp “mỗi vị trí đổi với một vị trí bất kỳ trong toàn dãy” không tự có cùng phân bố hoán vị.

Với nguồn lựa chọn công bằng phù hợp, thuật toán tạo các hoán vị vị trí với xác suất bằng nhau. Overload không truyền nguồn ngẫu nhiên được tài liệu mô tả là có xác suất xấp xỉ bằng nhau. Không dùng vài lần in thử để chứng minh một phân bố xác suất.

### Có thể giữ nguyên một phần hoặc toàn bộ thứ tự

Một vị trí có thể được chọn để đổi với chính nó. Hoán vị đồng nhất, nghĩa là dãy cuối trùng dãy đầu, vẫn là một kết quả hợp lệ.

Vì vậy các khẳng định sau đều sai:

- “Shuffle xong mọi phần tử phải đổi vị trí.”
- “Lần thứ hai bắt buộc khác lần thứ nhất.”
- “Cùng seed nhưng đổi đầu vào vẫn phải cho cùng dãy giá trị.”
- “Có hai phần tử giống nhau thì thuật toán sẽ loại bớt một.”

Với phần tử lặp, nhiều hoán vị vị trí có thể cho cùng dãy giá trị nhìn thấy. Nếu mọi phần tử đều bằng nhau, bạn không thể đòi quan sát một thứ tự giá trị khác dù các vị trí đã tham gia trộn.

### Không sort bằng một comparator ngẫu nhiên

Một comparator ngẫu nhiên không mô tả một quan hệ thứ tự nhất quán. Cùng một cặp có thể được so khác nhau ở các lần gọi; tính bắc cầu có thể bị phá.

Muốn trộn thì dùng shuffle. Muốn xếp theo một giá trị ưu tiên ngẫu nhiên cố định, cần xây dựng rõ các giá trị ấy và xử lý hòa theo yêu cầu; không để kết quả so sánh thay đổi mỗi lần comparator được gọi.

## 7. Seed giúp tái hiện điều gì?

~~~java
List<String> first = new ArrayList<>(original);
List<String> second = new ArrayList<>(original);

Collections.shuffle(first, new Random(17));
Collections.shuffle(second, new Random(17));
~~~

Hai nguồn `Random` được khởi tạo cùng seed; đầu vào hai list có cùng thứ tự. Trong cùng cách thực hiện, hai phép trộn tiêu thụ cùng chuỗi lựa chọn và cho cùng kết quả.

`Random` có hợp đồng rằng cùng seed và cùng chuỗi lời gọi phương thức tạo ra cùng chuỗi số. [API Random, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Random.html).

Các điều kiện phải cùng được giữ:

1. Dữ liệu đầu vào và thứ tự ban đầu giống nhau.
2. Nguồn ngẫu nhiên cùng loại, cùng trạng thái khởi đầu.
3. Chuỗi tiêu thụ số ngẫu nhiên giống nhau.
4. Cách trộn sử dụng chuỗi ấy giống nhau.

Nếu dùng một `Random` rồi gọi shuffle hai lần liên tiếp, lần hai bắt đầu từ trạng thái đã tiến đi. Nó không tương đương tạo `new Random(seed)` lại trước mỗi lần. Dùng chung nguồn cho nhiều tác vụ cũng làm lịch sử tiêu thụ ảnh hưởng kết quả.

Seed hữu ích để ghi lại một tình huống kiểm thử và tái hiện lỗi. Nó không có nghĩa kết quả trộn là một định dạng dữ liệu lâu dài được cố định qua mọi thay đổi của thuật toán thư viện. Khi cần khôi phục chính xác một thứ tự đã công bố, lưu chính thứ tự hoặc các định danh tương ứng là yêu cầu khác với chỉ lưu seed.

`java.util.Random` tạo số giả ngẫu nhiên và không phù hợp cho yêu cầu mật mã. Bài này dùng nó cho thí nghiệm tái hiện và kiểm thử, không suy rộng thành bảo đảm cho mọi cơ chế bốc chọn có yêu cầu riêng.

## 8. `null` và các quy tắc đảo giảm dần

### Đặt chính sách `null` vào comparator

Một list có thể cho chứa `null` nhưng thứ tự tự nhiên không cung cấp vị trí hợp lệ cho `null` khi cần so sánh nó với số. Nếu dữ liệu có `null`, dùng comparator có chính sách rõ:

~~~java
Comparator<Integer> ascendingNullLast =
        Comparator.nullsLast(Comparator.naturalOrder());

Collections.sort(values, ascendingNullLast);
~~~

Với dữ liệu `[3, null, 1]`, kết quả là `[1, 3, null]`.

Không tạo nguồn thử bằng `List.of(3, null, 1)` vì factory ấy đã từ chối `null` trước khi đến bước sort. Chương trình dùng `Arrays.asList` rồi sao chép sang `ArrayList` để kiểm tra đúng bước sắp xếp.

Truyền comparator `null` cho `Collections.sort(list, null)` có nghĩa dùng thứ tự tự nhiên; nó không có nghĩa tự biết cách xếp các phần tử `null`.

### Đảo toàn quy tắc khác với đảo phần giá trị không `null`

Nếu reverse toàn list `[1, 3, null]`, kết quả là `[null, 3, 1]`. Muốn số giảm dần nhưng `null` vẫn cuối, hãy dùng:

~~~java
Comparator<Integer> descendingNullLast =
        Comparator.nullsLast(Comparator.reverseOrder());
~~~

Khi ấy kết quả là `[3, 1, null]`.

Tương tự, gọi `reversed()` trên toàn comparator đã có `nullsLast` đảo cả quy tắc đặt `null`. Phải chọn đúng tầng đảo theo yêu cầu.

## 9. Chỉ xử lý một đoạn bằng `subList`

Một list có thể có phần đầu/cuối cần giữ nguyên, còn đoạn ở giữa cần xếp:

~~~java
List<String> items =
        new ArrayList<>(List.of("left", "c", "a", "b", "right"));

Collections.sort(items.subList(1, 4));
~~~

`subList(1, 4)` gồm chỉ số 1, 2, 3; cận cuối 4 không được lấy. Nó là view trên đoạn của list nguồn, nên sắp xếp view thay các vị trí tương ứng trong nguồn.

Kết quả nguồn là `[left, a, b, c, right]`. Có thể reverse hoặc shuffle chính view ấy nếu các quyền sửa được hỗ trợ.

Đừng tưởng `subList` là một bản sao để thử nghiệm riêng. Nếu cần tách khỏi nguồn, tạo `new ArrayList<>(source.subList(from, to))` trước khi xử lý.

Trong khi sử dụng view, không tự thêm/xóa cấu trúc nguồn qua một đường khác rồi tiếp tục dựa vào view cũ. Quyền sở hữu và vòng đời của view vẫn cần được kiểm soát; thuật toán đổi thứ tự không loại bỏ hợp đồng ấy. [API List.subList, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#subList(int,int)).

## 10. Chương trình hoàn chỉnh và stdout chính xác

Lưu mã sau vào **`ListOrderingDemo.java`**. Kiểu `Attempt` là record có hai trường; chương trình chỉ dùng số và chuỗi ổn định làm dữ liệu so sánh.

Stdout không chứa một dãy trộn ngẫu nhiên mặc định cần đoán trước. Thay vào đó, phần shuffle kiểm tra số lần xuất hiện của từng giá trị, tính bằng nhau khi dùng hai nguồn cùng seed, và việc nguồn ban đầu còn nguyên.

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Comparator;
import java.util.LinkedList;
import java.util.List;
import java.util.Map;
import java.util.Random;
import java.util.TreeMap;

public class ListOrderingDemo {
    record Attempt(String id, int points) {
        @Override
        public String toString() {
            return id + ":" + points;
        }
    }

    private static Map<String, Integer> counts(List<String> values) {
        Map<String, Integer> result = new TreeMap<>();
        for (String value : values) {
            result.merge(value, 1, Integer::sum);
        }
        return result;
    }

    private static void rejects(String label, Runnable action) {
        try {
            action.run();
            throw new AssertionError(label + " unexpectedly succeeded");
        } catch (UnsupportedOperationException ex) {
            System.out.println(label + "=UnsupportedOperationException");
        }
    }

    public static void main(String[] args) {
        List<Integer> source = List.of(4, 1, 3, 1, 2);
        List<Integer> reversed = new ArrayList<>(source);
        Collections.reverse(reversed);
        List<Integer> ascending = new ArrayList<>(source);
        Collections.sort(ascending);
        List<Integer> descending = new ArrayList<>(source);
        Collections.sort(descending, Comparator.reverseOrder());
        System.out.println("numbers.source=" + source);
        System.out.println("numbers.reversed=" + reversed);
        System.out.println("numbers.asc=" + ascending);
        System.out.println("numbers.desc=" + descending);

        List<Attempt> attempts = List.of(
                new Attempt("B", 2),
                new Attempt("D", 1),
                new Attempt("A", 2),
                new Attempt("C", 1));
        Comparator<Attempt> byPoints =
                Comparator.comparingInt(Attempt::points);
        List<Attempt> stableAscending = new ArrayList<>(attempts);
        Collections.sort(stableAscending, byPoints);
        List<Attempt> reverseAfterSort = new ArrayList<>(stableAscending);
        Collections.reverse(reverseAfterSort);
        List<Attempt> stableDescending = new ArrayList<>(attempts);
        Collections.sort(stableDescending, byPoints.reversed());
        List<Attempt> descendingThenId = new ArrayList<>(attempts);
        Collections.sort(descendingThenId,
                byPoints.reversed().thenComparing(Attempt::id));
        System.out.println("attempts.original=" + attempts);
        System.out.println("attempts.asc=" + stableAscending);
        System.out.println("attempts.ascThenReverse=" + reverseAfterSort);
        System.out.println("attempts.descStable=" + stableDescending);
        System.out.println("attempts.descThenId=" + descendingThenId);

        List<Integer> nullable =
                new ArrayList<>(Arrays.asList(3, null, 1));
        Collections.sort(nullable,
                Comparator.nullsLast(Comparator.naturalOrder()));
        System.out.println("nulls.ascLast=" + nullable);
        Collections.reverse(nullable);
        System.out.println("nulls.reverseWhole=" + nullable);
        List<Integer> descendingNullLast =
                new ArrayList<>(Arrays.asList(3, null, 1));
        Collections.sort(descendingNullLast,
                Comparator.nullsLast(Comparator.reverseOrder()));
        System.out.println("nulls.descLast=" + descendingNullLast);

        Integer[] backing = {3, 1, 2};
        List<Integer> fixed = Arrays.asList(backing);
        Collections.sort(fixed);
        System.out.println("fixed.afterSort=" + Arrays.toString(backing));
        Collections.reverse(fixed);
        System.out.println("fixed.afterReverse=" + Arrays.toString(backing));
        Collections.shuffle(fixed, new Random(17));
        List<Integer> fixedCheck = new ArrayList<>(fixed);
        Collections.sort(fixedCheck);
        System.out.println("fixed.shufflePreserves="
                + fixedCheck.equals(List.of(1, 2, 3)));

        List<String> window =
                new ArrayList<>(List.of("left", "c", "a", "b", "right"));
        Collections.sort(window.subList(1, 4));
        System.out.println("window.afterSort=" + window);
        Collections.reverse(window.subList(1, 4));
        System.out.println("window.afterReverse=" + window);

        List<String> original = List.of("A", "B", "A", "C", "D");
        List<String> first = new ArrayList<>(original);
        List<String> second = new ArrayList<>(original);
        Collections.shuffle(first, new Random(17));
        Collections.shuffle(second, new Random(17));
        System.out.println("shuffle.sameSeed=" + first.equals(second));
        if (!counts(first).equals(counts(original))) {
            throw new AssertionError("shuffle changed multiplicities");
        }
        System.out.println("shuffle.counts=" + counts(first));
        System.out.println("shuffle.source=" + original);
        List<String> defaultRandom = new ArrayList<>(original);
        Collections.shuffle(defaultRandom);
        System.out.println("shuffle.defaultPreserves="
                + counts(defaultRandom).equals(counts(original)));

        List<Integer> linked =
                new LinkedList<>(List.of(1, 2, 3, 4, 5, 6, 7, 8));
        Collections.shuffle(linked, new Random(17));
        Collections.sort(linked);
        System.out.println("linked.afterShuffleThenSort=" + linked);

        List<Integer> twice = new ArrayList<>(source);
        Collections.reverse(twice);
        Collections.reverse(twice);
        System.out.println("reverse.twice=" + twice.equals(source));

        List<Integer> readonly = List.of(3, 1, 2);
        rejects("sort.readonly", () -> Collections.sort(readonly));
        rejects("reverse.readonly", () -> Collections.reverse(readonly));
        rejects("shuffle.readonly",
                () -> Collections.shuffle(readonly, new Random(17)));

        List<String> empty = new ArrayList<>();
        Collections.sort(empty);
        Collections.reverse(empty);
        Collections.shuffle(empty, new Random(17));
        System.out.println("empty.size=" + empty.size());
        List<String> single = new ArrayList<>(List.of("only"));
        Collections.sort(single);
        Collections.reverse(single);
        Collections.shuffle(single, new Random(17));
        System.out.println("single.value=" + single);
    }
}
~~~

Biên dịch và chạy tại thư mục chứa tệp:

~~~shell
javac --release 17 -encoding UTF-8 ListOrderingDemo.java
java ListOrderingDemo
~~~

Cần JDK 17 trở lên cho lệnh biên dịch này. Mã đã được biên dịch với `--release 17` và chạy trên OpenJDK 24.0.2, thoát thành công với stdout chính xác sau:

~~~text
numbers.source=[4, 1, 3, 1, 2]
numbers.reversed=[2, 1, 3, 1, 4]
numbers.asc=[1, 1, 2, 3, 4]
numbers.desc=[4, 3, 2, 1, 1]
attempts.original=[B:2, D:1, A:2, C:1]
attempts.asc=[D:1, C:1, B:2, A:2]
attempts.ascThenReverse=[A:2, B:2, C:1, D:1]
attempts.descStable=[B:2, A:2, D:1, C:1]
attempts.descThenId=[A:2, B:2, C:1, D:1]
nulls.ascLast=[1, 3, null]
nulls.reverseWhole=[null, 3, 1]
nulls.descLast=[3, 1, null]
fixed.afterSort=[1, 2, 3]
fixed.afterReverse=[3, 2, 1]
fixed.shufflePreserves=true
window.afterSort=[left, a, b, c, right]
window.afterReverse=[left, c, b, a, right]
shuffle.sameSeed=true
shuffle.counts={A=2, B=1, C=1, D=1}
shuffle.source=[A, B, A, C, D]
shuffle.defaultPreserves=true
linked.afterShuffleThenSort=[1, 2, 3, 4, 5, 6, 7, 8]
reverse.twice=true
sort.readonly=UnsupportedOperationException
reverse.readonly=UnsupportedOperationException
shuffle.readonly=UnsupportedOperationException
empty.size=0
single.value=[only]
~~~

### Giải thích các nhóm kết quả

**`numbers`:** reverse được áp dụng lên bản sao của dãy chưa sort nên kết quả không giảm dần. Hai bản sort tăng và giảm dùng tiêu chí phù hợp. Nguồn có hai số 1 và các bản đều giữ số lần xuất hiện.

**`attempts`:** sort tăng giữ D trước C, B trước A. Reverse kết quả ấy đảo các nhóm hòa. Sort giảm trực tiếp từ đầu vào giữ B trước A, D trước C. Khi bổ sung tiêu chí mã tăng, thứ tự hòa được xác định bởi mã thay vì thứ tự gốc.

**`nulls`:** reverse toàn dãy đưa `null` từ cuối lên đầu; comparator giảm dành riêng cho phần không `null` giữ `null` cuối như yêu cầu.

**`fixed`:** list có kích thước cố định vẫn cho thay vị trí. Hai dòng đầu in lại mảng nguồn để chứng minh tác động qua view. Phần shuffle kiểm tra lại tập phần tử có số lần xuất hiện, không khẳng định một hoán vị cụ thể.

**`window`:** sort và reverse đoạn giữa tác động vào cùng list nguồn, còn hai phần tử biên giữ nguyên.

**`shuffle`:** hai phép trộn cùng điều kiện cho kết quả bằng nhau. Bảng đếm có hai A và một B, C, D. Phép trộn mặc định cũng giữ số lần xuất hiện dù dãy giá trị ngẫu nhiên không được in. Nguồn `original` không đổi vì các phép trộn dùng bản sao.

**`linked`:** shuffle cũng làm việc với `LinkedList` sửa được. Sort sau đó phục hồi thứ tự tăng của các giá trị; dòng này kiểm tra nội dung, không là một phép đo hiệu năng.

**`reverse.twice`:** hai lần đảo liên tiếp phục hồi dãy ban đầu.

**Các dòng ngoại lệ:** list do `List.of` tạo không hỗ trợ thay vị trí. Chương trình kiểm tra riêng từng thuật toán trên dữ liệu có nhiều phần tử, không dùng trường hợp không cần thao tác để đoán quyền sửa.

**`empty` và `single`:** các list làm việc sửa được ở hai biên 0 và 1 phần tử vẫn hợp lệ. Không cần viết nhánh đặc biệt chỉ để tránh một thao tác đổi thứ tự trên chúng.

## 11. Cơ chế, chi phí và giới hạn cần biết

### Sort phụ thuộc cả list lẫn comparator

Với các list tiêu chuẩn thường dùng, sắp xếp so sánh thường có chi phí cỡ `O(n log n)`; cách triển khai thích nghi có thể tận dụng dữ liệu đã có trật tự. Không lấy công thức ấy làm lời hứa cho mọi lớp list tùy chỉnh hoặc comparator có công việc tốn kém.

Nếu mỗi lần so sánh lại đọc tệp, gọi dịch vụ hoặc tính một giá trị đắt, chi phí comparator có thể chi phối tổng thời gian. Nên xác định khóa so sánh ổn định trước khi sort nếu mô hình cho phép.

Tài liệu `List.sort` mô tả việc dùng mảng trung gian ở cách thực hiện mặc định để tránh sắp xếp dựa trên truy cập chỉ số chậm của list liên kết. Nó cũng mô tả thuật toán thích nghi, ổn định. Đây là thông tin về cách thực hiện, không phải yêu cầu mọi list phải giữ một lớp thuật toán cụ thể.

### Reverse và shuffle có công việc tuyến tính trong triển khai tiêu chuẩn

Reverse cần đổi các cặp vị trí đối xứng. Shuffle cần chốt dần các vị trí. `Collections` mô tả hai thao tác với thời gian tuyến tính.

Với list lớn không có `RandomAccess`, cách thực hiện shuffle có thể đưa dữ liệu sang mảng, trộn rồi ghi trở lại, tránh truy cập chỉ số lặp dẫn tới chi phí bậc hai. Vì thế “sửa list được truyền vào” không có nghĩa “không bao giờ cấp phát bộ nhớ tạm”. [Cơ chế shuffle trong Collections, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#shuffle(java.util.List,java.util.Random)).

Đối với `ArrayList`, truy cập vị trí có chi phí hằng theo hợp đồng của lớp. Đối với `LinkedList`, truy cập bằng chỉ số phải đi qua các nút. Không tự viết một vòng `get(i)`/`set(i)` rồi mặc định nó có cùng chi phí trên cả hai. [ArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html), [LinkedList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedList.html).

### Không có bảo đảm rollback nếu thao tác thất bại

Một comparator có thể ném lỗi giữa quá trình so sánh; một list tùy chỉnh cũng có thể từ chối một bước sửa. Đừng dựa vào giả định rằng có ngoại lệ thì đầu vào chắc chắn giữ nguyên như trước.

Nếu cần bảo vệ list gốc khỏi quá trình sắp xếp có thể thất bại, xử lý một bản làm việc rồi chỉ công bố kết quả khi thành công. Comparator vẫn phải không tạo tác dụng phụ lên các phần tử chia sẻ.

### Cần phối hợp nếu list được dùng đồng thời

Đổi thứ tự là một quá trình gồm nhiều bước. Không cho luồng khác tùy ý đọc/ghi cùng list giữa quá trình rồi coi kết quả là một ảnh chụp nhất quán.

Một lớp bọc đồng bộ từng phương thức không tự biến mọi chuỗi thao tác nhiều bước thành một giao dịch theo yêu cầu nghiệp vụ. Khi cần, áp dụng một giao thức sở hữu/khóa cho toàn quá trình hoặc tạo bản làm việc có quyền sở hữu riêng rồi công bố kết quả phù hợp.

Không dùng `ConcurrentModificationException` làm cơ chế bảo vệ dữ liệu. Phát hiện sửa ngoài dự kiến không thay thế sự phối hợp đúng.

## 12. Kiểm thử đúng thứ cần bảo đảm

### Với sort

Kiểm tra kết quả theo comparator và kiểm tra các phần tử không bị thiếu/thừa. Nếu tính ổn định quan trọng, tạo ít nhất hai phần tử phân biệt được nhưng comparator trả 0 để quan sát thứ tự tương đối.

Nếu có nhiều tiêu chí, chọn dữ liệu có hòa ở tiêu chí đầu và khác ở tiêu chí sau. Nếu mọi điểm đều khác nhau, kiểm thử sẽ không phát hiện việc đảo sai tiêu chí phụ.

### Với reverse

Kiểm tra ánh xạ vị trí hoặc một dãy kỳ vọng cụ thể. Thử cả số phần tử chẵn và lẻ khi tự viết thuật toán. Tính chất reverse hai lần về ban đầu hữu ích nhưng chưa đủ để chứng minh một thuật toán bất kỳ là reverse: một hàm không làm gì cũng thỏa tính chất đó.

Chương trình trong bài có cả kết quả reverse cụ thể và tính chất hai lần đảo để tránh dựa vào một bằng chứng quá yếu.

### Với shuffle

Kiểm tra kích thước và số lần xuất hiện của từng phần tử. Chỉ chuyển list thành set rồi so không đủ: `[A, A, B]` và `[A, B, B]` có cùng tập thành viên nhưng số lần xuất hiện khác.

Dùng seed có kiểm soát khi cần tái hiện một tình huống. Không kiểm tra “thứ tự phải khác trước” vì hoán vị ban đầu hợp lệ. Không chứng minh phân bố công bằng bằng một lần hoặc vài lần chạy.

Một kiểm thử thuộc tính như “giữ các phần tử” cũng chưa đủ tự chứng minh thuật toán đã trộn đúng phân bố: một hàm không làm gì vẫn giữ phần tử. Tính đúng của cơ chế lựa chọn phải dựa vào thuật toán và hợp đồng nguồn ngẫu nhiên, còn thí nghiệm hỗ trợ phát hiện lỗi triển khai cụ thể.

## 13. Thực hành có đáp án

### Bài 1 — Reverse có làm giảm dần không?

Đầu vào `[2, 5, 1, 4]` được đưa thẳng cho `Collections.reverse`.

**Câu hỏi:** Kết quả là gì? Muốn giảm dần theo số thì dùng gì?

**Đáp án:** Kết quả là `[4, 1, 5, 2]`, không phải thứ tự giảm. Dùng `Collections.sort(list, Comparator.reverseOrder())` trên list sửa được để có `[5, 4, 2, 1]`. Reverse chỉ phụ thuộc thứ tự vị trí hiện có.

### Bài 2 — Giữ thứ tự tiếp nhận khi bằng điểm

Dữ liệu theo thứ tự `P:2, Q:1, R:2, S:1`. Yêu cầu điểm giảm dần và cùng điểm giữ thứ tự tiếp nhận.

**Câu hỏi:** Sort tăng rồi reverse cho kết quả nào? Sort giảm trực tiếp cho kết quả nào?

**Đáp án:** Sort tăng ổn định cho `Q:1, S:1, P:2, R:2`; reverse tiếp cho `R:2, P:2, S:1, Q:1`, không giữ thứ tự hòa ban đầu. Sort trực tiếp bằng comparator điểm giảm cho `P:2, R:2, Q:1, S:1` và đáp ứng yêu cầu.

### Bài 3 — Đặt `reversed` ở đâu?

Yêu cầu điểm giảm dần nhưng tên tăng dần khi bằng điểm.

**Câu hỏi:** Hai comparator sau có cùng ý nghĩa không?

~~~java
Comparator<Attempt> a =
        Comparator.comparingInt(Attempt::points)
                .reversed()
                .thenComparing(Attempt::id);

Comparator<Attempt> b =
        Comparator.comparingInt(Attempt::points)
                .thenComparing(Attempt::id)
                .reversed();
~~~

**Đáp án:** Không. `a` đảo tiêu chí điểm rồi thêm mã tăng. `b` đảo cả quy tắc đã ghép, nên khi bằng điểm thì mã giảm. Đây là thay đổi yêu cầu sắp xếp, không chỉ khác cách viết.

### Bài 4 — Cố định kích thước nhưng có thể đổi thứ tự

~~~java
Integer[] array = {2, 3, 1};
List<Integer> values = Arrays.asList(array);
Collections.sort(values);
Collections.reverse(values);
~~~

**Câu hỏi:** Mảng cuối là gì? Vì sao không cần `add`?

**Đáp án:** Mảng cuối là `[3, 2, 1]`. Các thao tác chỉ thay giá trị tại những ô sẵn có; list hỗ trợ thay phần tử và ghi xuyên tới mảng. Kích thước vẫn là 3. Điều đó không áp dụng cho một list không sửa được chỉ vì nó cũng có kích thước 3.

### Bài 5 — Cùng seed là chưa đủ

Hai list có cùng tập các chuỗi nhưng thứ tự đầu vào khác nhau. Mỗi list được shuffle bằng một `new Random(42)` riêng.

**Câu hỏi:** Có được khẳng định hai kết quả phải có cùng dãy giá trị không? Nếu cần tái hiện, lưu điều gì?

**Đáp án:** Không. Cùng chuỗi lựa chọn vị trí áp dụng lên hai thứ tự đầu vào khác nhau không nhất thiết cho cùng dãy giá trị. Để tái hiện thí nghiệm, giữ cả dữ liệu và thứ tự đầu vào, seed, loại nguồn và cách tiêu thụ nguồn. Nếu cần bảo tồn một thứ tự đã công bố lâu dài, lưu chính thứ tự hoặc các định danh của nó.

### Bài 6 — Shuffle có bắt buộc làm dãy đổi không?

Đầu vào là `[A, A, A]`. Kiểm thử yêu cầu kết quả phải khác đầu vào và mỗi phần tử phải chuyển vị trí.

**Câu hỏi:** Yêu cầu ấy có đúng hợp đồng không?

**Đáp án:** Không. Mọi hoán vị vị trí đều cho cùng dãy giá trị `[A, A, A]`. Ngay cả khi các phần tử phân biệt được, vẫn có thể có vị trí giữ nguyên và có thể gặp hoán vị đồng nhất. Kiểm tra giữ số lần xuất hiện và dùng thuật toán/nguồn ngẫu nhiên có hợp đồng phù hợp, không đòi một kết quả khác bắt buộc.

### Bài 7 — `null` cuối nhưng giá trị giảm

Có list sửa được chứa `[null, 2, 1]`. Yêu cầu kết quả `[2, 1, null]`.

**Câu hỏi:** Sort tăng với `nullsLast` rồi reverse có đúng không? Viết comparator phù hợp.

**Đáp án:** Không; sort tăng cho `[1, 2, null]` rồi reverse đưa `null` lên đầu. Dùng `Comparator.nullsLast(Comparator.reverseOrder())` để đảo thứ tự các số và giữ chính sách `null` cuối.

### Bài 8 — View hay bản riêng?

~~~java
List<String> source =
        new ArrayList<>(List.of("L", "b", "a", "R"));
List<String> middle = source.subList(1, 3);
Collections.sort(middle);
~~~

**Câu hỏi:** `source` trở thành gì? Nếu cần giữ nguyên nguồn thì tạo `middle` thế nào?

**Đáp án:** Nguồn thành `[L, a, b, R]` vì `middle` là view của hai vị trí 1 và 2. Cần tạo `new ArrayList<>(source.subList(1, 3))` trước khi sort để có list riêng về thứ tự. Bản sao vẫn chia sẻ các phần tử nếu chúng là đối tượng sửa được; trong ví dụ các phần tử là chuỗi.

Khi xử lý thứ tự, hãy xác định tiêu chí hoặc phép hoán vị cần có, quyền sửa list và nguồn dữ liệu phải giữ nguyên. Sort dùng quan hệ so sánh, reverse dùng vị trí hiện tại, shuffle dùng các lựa chọn ngẫu nhiên; những khác biệt ấy quyết định cả cách viết lẫn cách kiểm chứng.
