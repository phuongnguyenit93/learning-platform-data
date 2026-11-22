# Kiểu thực của mảng, ArrayStoreException và phần tử null kết thúc

## 1. Vì sao chuyển Collection thành mảng vẫn cần hiểu kiểu dữ liệu?

Một danh sách có thể được xây dựng từng phần tử, còn một API khác lại yêu cầu nhận `String[]`, `Number[]` hoặc một mảng có sẵn để ghi kết quả. `toArray` là cầu nối giữa hai cách biểu diễn đó. Tuy nhiên, lấy đủ các giá trị chưa phải toàn bộ công việc: mảng kết quả phải có **kiểu thành phần lúc chạy phù hợp**, có đủ vị trí để chứa dữ liệu, và có ranh giới rõ ràng giữa dữ liệu vừa chép với phần dư của một mảng được dùng lại.

Ba câu hỏi của bài này là:

1. Mảng thật sự được tạo là `Object[]`, `String[]` hay một kiểu khác?
2. Điều gì xảy ra nếu có phần tử không thể lưu vào kiểu mảng được yêu cầu?
3. Khi mảng đích dài hơn số phần tử, ô `null` đặt sau dữ liệu có ý nghĩa gì?

Hãy hình dung một khay lưu trữ ghi rõ “chỉ chứa chuỗi”, gồm năm ô. Ta đưa vào hai tên người. Hai tên được xếp ở đầu; ô thứ ba được đặt `null` để đánh dấu điểm ngay sau dữ liệu đã chép. Nhãn “chỉ chứa chuỗi” của khay vẫn tồn tại, dù người cầm khay đang gọi nó chung là “khay chứa đối tượng”. Nếu cố ghi thêm một số nguyên vào khay ấy, vấn đề nằm ở loại khay thật sự, không phải tên biến đang cầm nó.

Bài học dùng các phép chuyển đổi từ `Collection` sang mảng tham chiếu trong Java 17. Nó không biến `List<Integer>` thành `int[]` và không xem việc chuyển sang mảng là một phép chuyển đổi giá trị, chẳng hạn tự đổi số `42` thành chuỗi `"42"`.

## 2. Nhận diện ba dạng toArray

`toArray()` trả về `Object[]`; `toArray(T[] array)` dùng lại mảng đầu vào nếu đủ chỗ hoặc cấp phát mảng khác có **cùng kiểu thực**; `toArray(IntFunction<T[]>)` yêu cầu một hàm tạo mảng có kiểu tương ứng (dạng mặc định của `Collection` truyền đối số `0` tới hàm này). Không dạng nào tự chuyển từng `Integer` thành `int`.

Bài trước đối chiếu cú pháp và các nhánh tạo mảng. Ở đây sẽ kiểm tra ba hệ quả sâu hơn: kiểu thực của nơi chứa, vị trí `null` kết thúc khi dùng lại bộ đệm lớn, và tác động của `ArrayStoreException` trong lúc chép.

## 3. Kiểu của biến không thay đổi kiểu thật của mảng

### 3.1. Mỗi mảng có kiểu thành phần lúc chạy

Trong đoạn minh họa:

~~~java
Object[] values = new String[3];
~~~

kiểu khai báo của biến là `Object[]`, nhưng đối tượng mảng được tạo bởi `new String[3]` vẫn là `String[]`. Nó có ba vị trí, mỗi vị trí có thể chứa một tham chiếu `String` hoặc `null`.

Có thể đọc `values[0]` dưới dạng `Object`. Nhưng điều đó không có nghĩa được ghi mọi `Object` vào mảng:

~~~java
values[0] = "A";  // Hợp lệ.
values[1] = 42;   // ArrayStoreException khi chạy.
~~~

Số `42` được đóng gói thành `Integer`. Nó phù hợp với kiểu `Object` của biểu thức truy cập qua biến, nhưng không phù hợp với kiểu thành phần `String` của mảng thật sự.

Java kiểm tra việc lưu phần tử vào mảng tham chiếu lúc chạy; giá trị không tương thích làm phát sinh `ArrayStoreException`. [Java Language Specification 17 — Array Store Exception](https://docs.oracle.com/javase/specs/jls/se17/html/jls-10.html#jls-10.5).

Có thể kiểm tra kiểu để học hoặc chẩn đoán:

~~~java
System.out.println(values.getClass().getTypeName());
System.out.println(values.getClass().getComponentType().getTypeName());
~~~

Hai dòng lần lượt là `java.lang.String[]` và `java.lang.String`. Tên kiểu được in giúp thấy đối tượng thật sự đã được tạo. Trong mã ứng dụng thông thường, cách tạo mảng rõ ràng và hợp đồng kiểu vẫn quan trọng hơn việc liên tục dò kiểu rồi thử ghi.

### 3.2. Ép kiểu không phải là tạo một mảng mới

Đoạn sau là minh họa gây lỗi:

~~~java
Object[] plain = names.toArray();
String[] wrong = (String[]) plain;
~~~

`plain` giữ mảng thật sự có kiểu `Object[]`. Phép ép kiểu yêu cầu JVM xác nhận chính đối tượng ấy có phải `String[]` hay không; nó không duyệt từng chuỗi rồi dựng lại một mảng `String[]`. Do đó, kết quả là `ClassCastException` ngay tại phép ép kiểu.

Đối chiếu hai lỗi:

| Lỗi | Đang kiểm tra điều gì? | Ví dụ |
| --- | --- | --- |
| `ClassCastException` | Đối tượng mảng có thể được nhìn bằng kiểu tham chiếu yêu cầu hay không | Ép một `Object[]` thật sự thành `String[]` |
| `ArrayStoreException` | Giá trị phần tử có thể được lưu vào kiểu thành phần thật của mảng hay không | Chép `Integer` vào `String[]` |

Cách sửa ở ví dụ trên là yêu cầu mảng đúng kiểu ngay từ `toArray`:

~~~java
String[] correct = names.toArray(String[]::new);
~~~

Không nên bọc phép ép kiểu sai trong `try/catch` rồi dùng mảng rỗng thay thế. Cách ấy bỏ mất dữ liệu mà chưa xử lý đúng yêu cầu chuyển đổi.

## 4. toArray(T[]) chọn mảng kết quả như thế nào?

Gọi `n` là số phần tử cần chép và `m` là độ dài mảng truyền vào. Khi nguồn ổn định và các phần tử đều tương thích kiểu, có ba tình huống.

| Điều kiện | Mảng được trả về | Dữ liệu và phần kết thúc |
| --- | --- | --- |
| `m < n` | Mảng mới, cùng kiểu thực với mảng đầu vào | Chứa đủ `n` phần tử |
| `m == n` | Chính mảng đầu vào | Vừa đủ `n` vị trí, không có ô bổ sung để đặt dấu kết thúc |
| `m > n` | Chính mảng đầu vào | Chép vào `0..n-1` và đặt `null` ở chỉ số `n` |

Đối với `ArrayList`, tài liệu nêu rõ việc dùng lại hoặc tạo mảng cùng kiểu thực, và quy tắc đặt `null` ngay sau cuối dữ liệu khi mảng dư chỗ. [Java SE 17 — ArrayList.toArray](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html#toArray(T[])).

### 4.1. Mảng nhỏ: phải dùng giá trị trả về

Đoạn minh họa:

~~~java
String[] small = {"old"};
String[] result = names.toArray(small);
~~~

Danh sách có hai phần tử nên `small` chỉ dài một không đủ. Mảng `result` chứa `[Lan, An]`, có kiểu thực `String[]`, và `result == small` là `false`. Mảng `small` vẫn là một đối tượng riêng; nó không tự dài ra.

Sai lầm thường gặp là bỏ giá trị trả về:

~~~java
String[] target = new String[0];
names.toArray(target);
// target vẫn tham chiếu mảng dài 0.
~~~

Mảng không được đổi độ dài tại chỗ. Nếu muốn biến `target` giữ mảng kết quả, cần gán lại:

~~~java
target = names.toArray(target);
~~~

Hoặc dùng `String[] result = names.toArray(String[]::new)` khi không có nhu cầu tái sử dụng mảng cũ.

Một mảng độ dài `0` trong `new String[0]` đóng vai trò chỉ định kiểu mà không cung cấp sẵn chỗ cho tên người. Nó không yêu cầu kết quả cũng phải dài `0`.

### 4.2. Mảng vừa đủ: dùng lại chính mảng đó

~~~java
String[] exact = {"old0", "old1"};
String[] result = names.toArray(exact);
~~~

`result == exact` là `true` và dữ liệu thành `[Lan, An]`. Không có chỉ số `2` trong mảng hai ô, nên không đặt thêm `null` sau hai tên.

Mảng Java đã có thuộc tính `length`; `null` kết thúc trong một mảng dư chỗ là quy tắc riêng của phép chép này. Nó không phải yêu cầu rằng mọi mảng kết quả đều phải có một ô `null` cuối cùng.

### 4.3. Mảng dư chỗ: một ranh giới dữ liệu trong vùng lưu trữ lớn hơn

~~~java
String[] large = {"old0", "old1", "old2", "old3", "old4"};
String[] result = names.toArray(large);
~~~

Trong chương trình minh chứng dùng `ArrayList`, kết quả là:

~~~text
[Lan, An, null, old3, old4]
~~~

Chỉ số `0` và `1` chứa hai tên. Chỉ số `2` được đặt `null` vì đây là vị trí ngay sau dữ liệu đã chép. Hai giá trị cũ ở phía sau vẫn còn trong cách cài đặt được chạy.

Điểm được hợp đồng yêu cầu là ô ngay sau dữ liệu, không phải việc xóa sạch mọi ô còn lại. Không được diễn giải toàn bộ `result.length` thành số phần tử mới của danh sách. Cũng không nên dựa vào quy tắc này như một cơ chế xóa dữ liệu cũ khỏi toàn bộ vùng dư.

Nếu bên nhận sẽ duyệt tất cả phần tử của mảng và cần đúng hai tên, truyền một mảng dài đúng hai là cách biểu đạt đơn giản hơn việc gửi cả bộ đệm năm ô rồi ngầm mong bên nhận bỏ qua đuôi.

## 5. Hiểu đúng phần tử null kết thúc

### 5.1. Chỉ số của ô kết thúc bằng số phần tử đã chép

Với hai tên và mảng năm ô:

~~~text
chỉ số             0      1      2       3       4
sau khi chép       Lan    An     null    old3    old4
vai trò            dữ liệu      kết thúc        vùng dư
~~~

Nói chính xác hơn, hai ô `0` và `1` là dữ liệu; ô `2` là vị trí kết thúc được quy định. Các ô sau đó thuộc phần dư của mảng đã tái sử dụng.

`null` tại chỉ số `2` không phải một phần tử được thêm vào `names`. Danh sách vẫn có `size() == 2`. Mảng vẫn có `length == 5`. Phép chuyển đổi không làm danh sách mọc thêm một phần tử chỉ để đánh dấu điểm cuối.

Nếu nguồn rỗng và mảng đích có ít nhất một ô, vị trí ngay sau dữ liệu là `0`. Vì vậy, ô đầu được đặt `null`. Trong ca thử với mảng ba ô, kết quả quan sát là `[null, old1, old2]`. Nếu cả nguồn và mảng đích đều có độ dài `0`, không có ô nào để ghi và cũng không cần tạo một ô đánh dấu riêng.

### 5.2. null trong dữ liệu khác null dùng làm ranh giới

Một danh sách có thể chứa `null`, nếu loại danh sách đó cho phép. Ví dụ:

~~~java
List<String> values = Arrays.asList("A", null, "B");
String[] target = {"old0", "old1", "old2", "old3", "old4"};
values.toArray(target);
~~~

Kết quả quan sát:

~~~text
[A, null, B, null, old4]
~~~

Có hai vai trò khác nhau:

- `target[1]` là phần tử `null` thật sự của danh sách.
- `target[3]` là ô ngay sau ba phần tử được chép, được đặt `null` do đích dư chỗ.

Nếu quét từ đầu và dừng ở `null` đầu tiên, thuật toán chỉ đọc được `A` rồi bỏ mất `B`. Kết quả tìm được `1` không phải kích thước của nguồn, vốn là `3`.

Dấu kết thúc chỉ có thể giúp suy ra độ dài theo cách quét tới `null` đầu tiên khi đã biết chắc dữ liệu không chứa `null`. Trong thiết kế có dữ liệu nullable, hãy giữ số lượng phần tử bằng một thông tin riêng hoặc dùng mảng kết quả có độ dài đúng nhu cầu.

### 5.3. Mảng mới cũng có null, nhưng lý do có thể khác

Java khởi tạo các vị trí của mảng tham chiếu mới bằng `null`. Do đó, nhìn thấy nhiều `null` ở đuôi một mảng mới chưa chứng minh rằng `toArray` đã chủ động ghi tất cả các ô ấy.

Để hiểu đúng quy tắc, ví dụ của bài cố ý điền dữ liệu cũ `old0`, `old1`... vào mảng đích trước khi chuyển đổi. Nhờ vậy, ta phân biệt được ô nào bị ghi đè, ô nào được đặt dấu kết thúc, và phần nào không thuộc dữ liệu mới.

Đây là một cách kiểm thử hữu ích khi mã sử dụng bộ đệm tái sử dụng: bắt đầu bằng dữ liệu cũ có thể nhận biết, thay vì dùng một bộ đệm vốn đã toàn `null` rồi suy ra rằng mọi ô dư đều được xóa.

## 6. ArrayStoreException trong lúc chuyển đổi

### 6.1. Kiểu của từng phần tử phải phù hợp mảng đích

Đoạn minh họa:

~~~java
Collection<Number> numbers = Arrays.<Number>asList(4, 2.5);

Number[] accepted = numbers.toArray(new Number[0]);
Integer[] rejected = numbers.toArray(new Integer[0]);
~~~

`Number[]` có thể chứa cả `Integer` và `Double`, nên mảng thứ nhất chứa `[4, 2.5]`. `Integer[]` không chứa được `Double`, nên lời gọi thứ hai gây `ArrayStoreException`.

`toArray` không làm các việc sau để cứu lời gọi thứ hai:

- Không cắt `2.5` thành `2`.
- Không gọi `intValue()` trên mỗi số.
- Không bỏ những phần tử không phù hợp.
- Không âm thầm đổi kết quả từ `Integer[]` sang `Number[]`.

Nếu cần mảng `Integer[]`, ứng dụng phải định nghĩa và thực hiện phép chuyển đổi giá trị trước. Việc làm tròn, cắt phần thập phân, kiểm tra tràn số hoặc từ chối dữ liệu đều là quyết định nghiệp vụ riêng.

### 6.2. Vì sao mã vẫn biên dịch?

Dạng `<T> T[] toArray(T[] a)` có tham số kiểu `T` của chính phương thức. Nó không có ràng buộc kiểu `T` buộc mọi phần tử của `Collection<E>` phải tương thích ngay từ lúc biên dịch. Sự tương thích cuối cùng được kiểm tra khi lưu các giá trị thực tế.

Do đó, một nguồn khai báo rộng có thể chuyển thành mảng hẹp nếu mọi phần tử thực tế đều phù hợp:

~~~java
List<Object> values = List.of("A", "B");
String[] strings = values.toArray(new String[0]);
~~~

Cả hai phần tử ở đây đều là `String` nên lời gọi chạy được. Nếu nguồn sau này có thêm một `Integer`, kết quả sẽ khác. Khả năng chạy được với một tập dữ liệu không tạo thành bảo đảm kiểu cho mọi giá trị được phép thêm vào một `List<Object>`.

Khi một API chỉ chấp nhận chuỗi, giữ nguồn ở kiểu `Collection<String>` và kiểm soát dữ liệu đi vào giúp mô hình rõ hơn. Nhưng ngay cả generic nguồn đúng cũng không biến mảng `Object[]` của dạng không tham số thành mảng `String[]`.

### 6.3. Biến Object[] vẫn có thể giữ một mảng hẹp

~~~java
Object[] target = new Integer[4];
numbers.toArray(target);
~~~

Biến `target` có kiểu nhìn từ mã là `Object[]`. Đối tượng thật sự vẫn là `Integer[]` nên vẫn không chứa được `Double`. Độ dài bốn đủ để chứa hai số không giải quyết được lỗi kiểu.

Phải tách hai điều kiện:

~~~text
đủ số ô?
    có thể chép đủ số phần tử

đúng kiểu thành phần?
    có thể lưu từng giá trị vào những ô ấy
~~~

Cả hai cần thỏa. Một mảng có rất nhiều ô nhưng kiểu quá hẹp vẫn không phù hợp. Một mảng đúng kiểu nhưng thiếu ô có thể được thay bằng mảng mới, vì phép tạo mảng mới vẫn giữ cùng kiểu thành phần mà bên gọi đã yêu cầu.

### 6.4. Nguồn rỗng và nguồn chỉ có null không kiểm tra được mọi lỗi kiểu

Nếu nguồn không có phần tử nào không tương thích, lỗi lưu kiểu không xuất hiện chỉ vì tham số generic trông khác nhau. Nguồn rỗng không có giá trị để lưu; `null` cũng có thể lưu vào mảng tham chiếu.

Vì vậy, kiểm thử duy nhất bằng danh sách rỗng có thể bỏ sót lỗi mà dữ liệu thật gây ra. Hãy thêm ít nhất một giá trị thuộc loại không phù hợp khi kiểm tra nhánh `ArrayStoreException`. Ngược lại, đừng xem `null` trong một danh sách cho phép `null` là nguyên nhân mặc định của lỗi lưu mảng.

## 7. Dạng hàm tạo mảng: rõ kiểu nhưng không bỏ kiểm tra

Cách viết:

~~~java
String[] result = names.toArray(String[]::new);
~~~

dùng một tham chiếu hàm tạo mảng. Khi nhận độ dài `n`, `String[]::new` có thể tạo một `String[n]`. Nó diễn tả rõ kiểu thành phần mong muốn mà không cần ép kết quả của `toArray()`.

Có thể chọn kiểu giao diện nếu các phần tử đều phù hợp:

~~~java
CharSequence[] result = names.toArray(CharSequence[]::new);
~~~

Các `String` lưu được trong `CharSequence[]`. Tuy nhiên, hàm tạo mảng không phải hàm chuyển đổi từng phần tử. Lệnh `names.toArray(Integer[]::new)` vẫn yêu cầu chép các chuỗi vào mảng `Integer[]` và gây `ArrayStoreException`.

Cách cài đặt mặc định của `Collection.toArray(IntFunction)` gọi hàm tạo với `0` rồi chuyển mảng đó cho dạng `toArray(T[])`. Đây là chi tiết được nêu cho cách cài đặt mặc định, không phải lý do để viết một hàm tạo bỏ qua độ dài hoặc tạo tác dụng phụ. Hãy dùng một hàm tạo trả về mảng mới đúng kiểu và đúng độ dài được yêu cầu. [Java SE 17 — Collection.toArray(IntFunction)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html#toArray(java.util.function.IntFunction)).

Không nên viết chương trình phụ thuộc vào giả định rằng mọi lớp triển khai đều sẽ gọi hàm tạo đúng một lần với kích thước bằng `size()`. API có thể có cách cài đặt riêng; đối với tác vụ chuyển đổi, tham chiếu hàm tạo thuần như `String[]::new` tránh được sự phụ thuộc không cần thiết ấy.

Bài này không kết luận rằng một cách viết luôn nhanh hơn cách khác. Quy tắc kiểu dữ liệu, giá trị trả về và khả năng dùng lại mảng cần được hiểu trước; so sánh hiệu năng chỉ có ý nghĩa khi đo trên phiên bản JDK và tải cụ thể.

## 8. Đừng nhầm ba ý nghĩa của null

| Vị trí của null | Ý nghĩa | Cách xử lý |
| --- | --- | --- |
| Một phần tử của nguồn | Dữ liệu nullable nếu cấu trúc cho phép | Chép như một giá trị tham chiếu hợp lệ; bên đọc phải xử lý |
| Ô ngay sau dữ liệu trong mảng đích dư chỗ | Ranh giới do `toArray(T[])` quy định | Không tính ô đó thành phần tử mới của nguồn |
| Chính tham số mảng hoặc hàm tạo bị null | Thiếu đối tượng để xác định/tạo mảng đích | `NullPointerException` |

Ví dụ nguồn có một phần tử `null` hoàn toàn khác với lời gọi:

~~~java
names.toArray((String[]) null);
~~~

Đây là đoạn minh họa gây `NullPointerException` vì chính mảng đích là `null`. Nó không yêu cầu “tạo một mảng chuỗi mặc định” và cũng không tạo danh sách có một `null`.

Tương tự, tham số hàm tạo `null` là không hợp lệ. Với Java 17 có cả hai overload một tham số, lệnh `names.toArray(null)` còn có thể gây lỗi chọn overload ở lúc biên dịch, vì `null` có thể khớp cả kiểu mảng lẫn kiểu `IntFunction`. Trong ví dụ kiểm tra ngoại lệ, bài ép kiểu tham số `null` một cách tường minh để kiểm tra đúng overload đang nói tới.

Tránh dùng `null` như một tín hiệu ngầm để chọn kiểu mảng. Hãy truyền `new String[0]`, `String[]::new` hoặc dùng dạng không tham số theo hợp đồng đầu ra cần có.

## 9. Lỗi khi chép vào mảng dùng lại có thể để lại dữ liệu dở dang

Nếu cung cấp một mảng đủ chỗ, phép chuyển đổi có thể đang ghi các phần tử thì gặp một giá trị không tương thích. Không nên xem `ArrayStoreException` như một cam kết rằng mảng đầu vào chắc chắn chưa bị thay đổi.

Ca minh họa dùng `ArrayList`:

~~~java
List<Object> mixed = new ArrayList<>(List.of("ok", 42, "later"));
String[] reused = {"old0", "old1", "old2", "old3", "old4"};

mixed.toArray(reused);
~~~

Phần tử `"ok"` có thể được chép vào ô đầu. Khi đến `42`, không thể lưu `Integer` vào `String[]`. Trong chương trình được chạy, sau khi bắt ngoại lệ, mảng còn:

~~~text
[ok, old1, old2, old3, old4]
~~~

Không được coi `reused[3]` là dấu kết thúc hợp lệ của một lần chuyển đổi thành công: lời gọi đã thất bại trước khi hoàn tất.

Mã nguồn OpenJDK 17 của `ArrayList.toArray(T[])` dùng phép chép mảng khi tái sử dụng vùng đích. Hành vi của `System.arraycopy` với phần tử tham chiếu không tương thích có thể chép được đoạn đầu rồi mới ném lỗi. [OpenJDK 17 — ArrayList.java](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/java/util/ArrayList.java), [Java SE 17 — System.arraycopy](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#arraycopy(java.lang.Object,int,java.lang.Object,int,int)).

Đây là giải thích cho ca thử cụ thể, không phải cam kết rằng mọi loại `Collection` phải để lại cùng một đoạn đầu khi lỗi.

Nếu mảng cũ đang là dữ liệu đã công bố và không được phép bị ghi dở, có thể tạo một kết quả mới trước:

~~~java
String[] next = source.toArray(String[]::new);
// Chỉ sử dụng hoặc công bố next sau khi lời gọi thành công.
~~~

`source` trong đoạn này là nguồn do ứng dụng cung cấp. Nếu lời gọi ném lỗi, không có giá trị `next` mới được gán bởi lần gọi đó. Thiết kế vẫn cần kiểm soát các tác dụng phụ khác và chính sách truy cập đồng thời nếu có; phép chuyển đổi đơn lẻ không cung cấp một giao dịch cho toàn bộ chương trình.

## 10. Mảng kết quả riêng không có nghĩa là sao chép sâu

Với cách tạo mảng kết quả mới, thay vị trí mảng không thay vị trí trong danh sách:

~~~java
String[] snapshot = names.toArray(String[]::new);
snapshot[0] = "Other";
~~~

`names` vẫn chứa `[Lan, An]`. Mảng `snapshot` có những vị trí riêng và trở thành `[Other, An]`.

Nhưng `toArray` chép các tham chiếu phần tử, không tự nhân bản từng đối tượng. Với phần tử sửa được:

~~~java
StringBuilder item = new StringBuilder("seed");
List<StringBuilder> items = List.of(item);
StringBuilder[] result = items.toArray(StringBuilder[]::new);

result[0].append("!");
~~~

`items.get(0)` cũng biểu diễn `seed!` vì cùng đối tượng `StringBuilder` đã bị sửa. Nếu thay `result[0]` bằng một `StringBuilder` khác, chỉ vị trí mảng kết quả thay đổi.

Sự khác biệt này liên quan trực tiếp tới cách hiểu “kiểu thực”: đối tượng mảng có kiểu thành phần riêng, và mỗi phần tử trong đó lại là một tham chiếu tới một đối tượng riêng. Kiểm tra kiểu khi lưu bảo đảm tham chiếu phù hợp loại mảng; nó không làm đối tượng phần tử trở nên bất biến.

Cũng cần phân biệt với `Arrays.asList(array)`: cách đó tạo một danh sách dùng chung các vị trí của mảng nền. `toArray` hướng ngược lại để lấy các phần tử ra mảng không nên bị hiểu là mọi phép chuyển đổi đều giữ cùng một cơ chế dùng chung.

## 11. Chương trình minh chứng đầy đủ

Lưu toàn bộ mã dưới đây thành **ToArrayRuntimeDemo.java**. Chương trình chỉ dùng thư viện chuẩn, tương thích Java 17.

`rejects` xác nhận lời gọi thất bại bằng loại ngoại lệ kỳ vọng; nó không chỉ in thông báo rồi bỏ qua mọi lỗi. Nếu không có ngoại lệ hoặc loại ngoại lệ khác, chương trình sẽ dừng để bộc lộ kết quả sai.

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collection;
import java.util.List;
import java.util.function.IntFunction;

public class ToArrayRuntimeDemo {
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
        List<String> names = new ArrayList<>(List.of("Lan", "An"));

        Object[] plain = names.toArray();
        System.out.println("plain-type=" + plain.getClass().getTypeName());
        System.out.println("plain-values=" + Arrays.toString(plain));
        rejects("cast-plain", ClassCastException.class, () -> {
            String[] wrong = (String[]) plain;
            System.out.println(wrong.length);
        });

        String[] typed = names.toArray(new String[0]);
        System.out.println("typed-type=" + typed.getClass().getTypeName());
        System.out.println("typed-values=" + Arrays.toString(typed));

        String[] small = {"old"};
        String[] grown = names.toArray(small);
        System.out.println("small-reused=" + (grown == small));
        System.out.println("small-original=" + Arrays.toString(small));
        System.out.println("small-result=" + Arrays.toString(grown));

        String[] exact = {"old0", "old1"};
        String[] exactResult = names.toArray(exact);
        System.out.println("exact-reused=" + (exactResult == exact));
        System.out.println("exact-values=" + Arrays.toString(exactResult));

        String[] large = {"old0", "old1", "old2", "old3", "old4"};
        String[] largeResult = names.toArray(large);
        System.out.println("large-reused=" + (largeResult == large));
        System.out.println("large-values=" + Arrays.toString(largeResult));

        String[] emptyTarget = {"old0", "old1", "old2"};
        List.<String>of().toArray(emptyTarget);
        System.out.println("empty-values=" + Arrays.toString(emptyTarget));

        List<String> nullable = Arrays.asList("A", null, "B");
        String[] nullableTarget = {"old0", "old1", "old2", "old3", "old4"};
        nullable.toArray(nullableTarget);
        int firstNull = 0;
        while (firstNull < nullableTarget.length && nullableTarget[firstNull] != null) {
            firstNull++;
        }
        System.out.println("nullable-values=" + Arrays.toString(nullableTarget));
        System.out.println("nullable-size=" + nullable.size() + " / first-null=" + firstNull);

        Collection<Number> numbers = Arrays.<Number>asList(4, 2.5);
        Number[] numeric = numbers.toArray(new Number[0]);
        System.out.println("number-type=" + numeric.getClass().getTypeName());
        System.out.println("number-values=" + Arrays.toString(numeric));
        rejects("integer-target", ArrayStoreException.class,
                () -> numbers.toArray(new Integer[0]));

        Object[] wideReference = new Integer[4];
        System.out.println("wide-reference-type=" + wideReference.getClass().getTypeName());
        rejects("wide-reference-target", ArrayStoreException.class,
                () -> numbers.toArray(wideReference));

        List<Object> stringObjects = List.of("A", "B");
        String[] narrowed = stringObjects.toArray(new String[0]);
        System.out.println("broad-source-values=" + Arrays.toString(narrowed));

        String[] generated = names.toArray(String[]::new);
        System.out.println("generator-type=" + generated.getClass().getTypeName());
        CharSequence[] sequences = names.toArray(CharSequence[]::new);
        System.out.println("interface-type=" + sequences.getClass().getTypeName());
        rejects("wrong-generator", ArrayStoreException.class,
                () -> names.toArray(Integer[]::new));
        rejects("null-array", NullPointerException.class,
                () -> names.toArray((String[]) null));
        rejects("null-generator", NullPointerException.class,
                () -> names.toArray((IntFunction<String[]>) null));

        List<Object> mixed = new ArrayList<>(List.of("ok", 42, "later"));
        String[] reused = {"old0", "old1", "old2", "old3", "old4"};
        rejects("partial-copy", ArrayStoreException.class, () -> mixed.toArray(reused));
        System.out.println("partial-target=" + Arrays.toString(reused));

        String[] snapshot = names.toArray(String[]::new);
        snapshot[0] = "Other";
        System.out.println("detached-slots=" + names + " / " + Arrays.toString(snapshot));

        StringBuilder item = new StringBuilder("seed");
        List<StringBuilder> items = List.of(item);
        StringBuilder[] itemArray = items.toArray(StringBuilder[]::new);
        itemArray[0].append("!");
        System.out.println("shared-item=" + items.get(0));
        itemArray[0] = new StringBuilder("other");
        System.out.println("replaced-slot=" + items.get(0) + " / " + itemArray[0]);
    }
}
~~~

Biên dịch và chạy:

~~~shell
javac --release 17 -encoding UTF-8 ToArrayRuntimeDemo.java
java ToArrayRuntimeDemo
~~~

Stdout chính xác:

~~~text
plain-type=java.lang.Object[]
plain-values=[Lan, An]
cast-plain -> ClassCastException
typed-type=java.lang.String[]
typed-values=[Lan, An]
small-reused=false
small-original=[old]
small-result=[Lan, An]
exact-reused=true
exact-values=[Lan, An]
large-reused=true
large-values=[Lan, An, null, old3, old4]
empty-values=[null, old1, old2]
nullable-values=[A, null, B, null, old4]
nullable-size=3 / first-null=1
number-type=java.lang.Number[]
number-values=[4, 2.5]
integer-target -> ArrayStoreException
wide-reference-type=java.lang.Integer[]
wide-reference-target -> ArrayStoreException
broad-source-values=[A, B]
generator-type=java.lang.String[]
interface-type=java.lang.CharSequence[]
wrong-generator -> ArrayStoreException
null-array -> NullPointerException
null-generator -> NullPointerException
partial-copy -> ArrayStoreException
partial-target=[ok, old1, old2, old3, old4]
detached-slots=[Lan, An] / [Other, An]
shared-item=seed!
replaced-slot=seed! / other
~~~

Mã đã biên dịch bằng `--release 17` và chạy trên JDK 24.0.2. Cờ biên dịch xác minh mức ngôn ngữ và API Java 17, không đồng nghĩa đã chạy bằng JVM 17.

Đọc kết quả theo từng nhóm:

- `plain-type` và `cast-plain` xác nhận kiểu mảng do dạng không tham số tạo ra và lỗi khi ép sai kiểu.
- `typed-type` xác nhận mảng có kiểu thành phần cụ thể.
- `small`, `exact` và `large` phân biệt tạo mảng mới với tái sử dụng; dấu `==` kiểm tra cùng đối tượng mảng, không kiểm tra nội dung.
- `empty-values` và `nullable-values` cho thấy `null` kết thúc phụ thuộc số phần tử đã chép, còn `null` trong dữ liệu không phải điểm dừng chung.
- `integer-target` và `wide-reference-target` chứng minh kiểu thật của mảng quyết định khả năng lưu giá trị.
- `broad-source-values` minh họa kiểu khai báo nguồn rộng vẫn có thể chứa toàn các chuỗi tương thích.
- `wrong-generator`, `null-array` và `null-generator` tách yêu cầu kiểu khỏi sự hợp lệ của tham số.
- `partial-target` là kết quả của ca lỗi cụ thể với `ArrayList`; không suy rộng thành bảo đảm về trạng thái sau lỗi của mọi cấu trúc.
- `detached-slots` và `shared-item` phân biệt vị trí mảng riêng với đối tượng phần tử được dùng chung.

Các phép chuyển đổi ở đây chạy tuần tự với nguồn ổn định. Không dùng kết quả này để suy ra ảnh chụp nhất quán khi một luồng khác đang sửa một collection không có hợp đồng đồng thời phù hợp.

## 12. Áp dụng đúng tại ranh giới API

Khi một phương thức nhận `String[]`, cách chuyển thường rõ nhất là tạo trực tiếp kiểu ấy:

~~~java
String[] arguments = names.toArray(String[]::new);
~~~

`arguments.length` phản ánh số tên trong ca chuyển đổi với hàm tạo chuẩn và nguồn ổn định. Bên nhận không phải quét tới `null` hoặc biết rằng một bộ đệm dư chỗ còn chứa dữ liệu cũ.

Nếu ứng dụng thật sự cần tái sử dụng mảng, cần giữ cả mảng trả về và số phần tử hợp lệ. Đoạn minh họa:

~~~java
// names ổn định trong suốt đoạn xử lý này.
int count = names.size();
String[] buffer = obtainBuffer();
buffer = names.toArray(buffer);
consumePrefix(buffer, count);
~~~

`obtainBuffer` và `consumePrefix` là các hàm do ứng dụng định nghĩa, nên đây không phải chương trình độc lập. Điều kiện “nguồn ổn định” quan trọng: gọi `size` rồi `toArray` là hai thao tác; nếu có thay đổi đồng thời không được phối hợp, không thể mặc nhiên coi số lượng cũ là độ dài dữ liệu của kết quả mới.

Hợp đồng `consumePrefix` cần nêu rằng chỉ các chỉ số `0` đến `count - 1` thuộc dữ liệu hợp lệ. Việc có một ô `null` sau dữ liệu không thay thế được thông tin số lượng khi nguồn có thể chứa `null`.

Ngoài ra, nếu bên nhận giữ mảng để dùng lâu dài, tái sử dụng cùng mảng đó cho lần chuyển đổi tiếp theo sẽ thay dữ liệu mà bên nhận đang thấy. Quyền sở hữu và thời gian sống của bộ đệm cần được quyết định riêng. `toArray` chỉ quy định phép chép; nó không tự quản lý các bên đang giữ tham chiếu mảng đích.

Khi xử lý số, chọn kiểu mảng chứa được dữ liệu hoặc chuyển đổi giá trị một cách tường minh. `Number[]` chứa được nhiều loại số; `Integer[]` chỉ phù hợp các giá trị có thể lưu như `Integer`. Không có overload `Collection.toArray` trực tiếp nhận `int[]` vì `T[]` ở đây là mảng của kiểu tham chiếu. Chuyển sang mảng nguyên thủy cần một bước chuyển đổi khác phù hợp mục tiêu, không phải ép kiểu mảng kết quả.

## 13. Thực hành có đáp án

### Bài 1 — Mọi phần tử đều là String có ép được không?

Cho `List<String> values = List.of("A", "B")`. Lệnh `String[] result = (String[]) values.toArray()` có hợp lệ lúc chạy không? Sửa thế nào?

**Đáp án:** Không, mảng của dạng `toArray()` có kiểu thực `Object[]` nên phép ép sang `String[]` gây `ClassCastException`. Dùng `values.toArray(String[]::new)` hoặc `values.toArray(new String[0])` để yêu cầu đúng kiểu mảng.

### Bài 2 — Bỏ qua giá trị trả về

Cho `String[] target = new String[1]` và danh sách có ba chuỗi. Sau `values.toArray(target)`, có thể đọc ba phần tử qua biến `target` không?

**Đáp án:** Không. Mảng ban đầu chỉ có một ô; `toArray` trả về mảng mới đủ chỗ nhưng biến `target` chưa được gán lại. Cần nhận giá trị trả về, ví dụ `target = values.toArray(target)`. Không thể làm một đối tượng mảng tự dài ra bằng cách gọi phương thức.

### Bài 3 — Điền chính xác ô kết thúc

Danh sách `[A, B]` được chép vào `String[] target = {"x0", "x1", "x2", "x3"}`. Ô nào bắt buộc được đặt `null` sau khi chuyển thành công? Có bảo đảm mọi ô dư đều được xóa không?

**Đáp án:** Ô chỉ số `2` là vị trí ngay sau hai phần tử và được đặt `null`. Hợp đồng không yêu cầu xóa toàn bộ đuôi. Trong ca `ArrayList` minh chứng, ô `3` vẫn giữ giá trị cũ. Không được coi toàn bộ mảng bốn ô là bốn phần tử dữ liệu mới.

### Bài 4 — null đầu tiên có phải độ dài không?

Nguồn là `[A, null, B]`, mảng kết quả dư chỗ thành `[A, null, B, null, old4]`. Quét tới `null` đầu tiên cho kết quả `1`. Vì sao đây không phải độ dài nguồn?

**Đáp án:** `null` ở chỉ số `1` là một phần tử thật sự của nguồn, còn ô kết thúc nằm ở chỉ số `3`. Dữ liệu có ba phần tử. Chỉ được dùng cách quét tới `null` đầu tiên khi đã có bảo đảm rằng phần dữ liệu không chứa `null`; nếu không, giữ số lượng riêng hoặc lấy mảng đúng kích thước.

### Bài 5 — Object[] nhưng vẫn ArrayStoreException

Cho `Collection<Number> numbers = Arrays.<Number>asList(1, 2.5)` và `Object[] target = new Integer[5]`. Vì sao `numbers.toArray(target)` không chạy được dù mảng đủ dài?

**Đáp án:** Đối tượng mảng thật sự là `Integer[]`. Phần tử `Double` không thể lưu vào đó. `Object[]` chỉ là kiểu của biến tham chiếu; nó không đổi kiểu mảng thật thành `Object[]`. Chọn `Number[]` nếu cần giữ cả hai loại số.

### Bài 6 — Chuyển đổi bằng hàm tạo có đổi từng giá trị không?

`List<Integer> values = List.of(1, 2)` rồi gọi `values.toArray(String[]::new)` có tạo `["1", "2"]` không?

**Đáp án:** Không. Hàm tạo chỉ xác định mảng `String[]`, không gọi `toString` trên phần tử. Việc chép các `Integer` vào mảng chuỗi gây `ArrayStoreException`. Nếu cần chuỗi, phải thực hiện phép chuyển từng giá trị sang chuỗi rồi mới tạo mảng phù hợp.

### Bài 7 — Chép thất bại có giữ nguyên mảng dùng lại không?

Một `ArrayList<Object>` chứa `["ok", 42, "later"]` được chép vào `String[]` đủ chỗ. Sau `ArrayStoreException`, có được mặc nhiên dùng mảng đích như thể nó chưa bị thay đổi không?

**Đáp án:** Không. Ca thử của bài cho thấy phần tử đầu đã được ghi trước khi gặp số không phù hợp. Hợp đồng không cung cấp cơ chế quay lui toàn bộ. Nếu không được phép ghi dở vào mảng đã công bố, tạo kết quả mới rồi chỉ sử dụng nó khi phép chuyển đổi thành công.

### Bài 8 — Mảng riêng có bảo vệ đối tượng bên trong không?

Danh sách chứa một `StringBuilder` được chuyển sang `StringBuilder[]` mới. Gọi `array[0].append("!")` rồi `array[0] = new StringBuilder("other")`. Hai thao tác ảnh hưởng danh sách gốc khác nhau thế nào?

**Đáp án:** `append` sửa đối tượng `StringBuilder` đang được cả hai nơi dùng chung, nên đọc phần tử ở danh sách cũng thấy thay đổi. Phép gán sau chỉ thay vị trí số `0` của mảng kết quả; nó không thay vị trí trong danh sách. `toArray` không tự tạo bản sao sâu cho phần tử.

## 14. Những câu hỏi cần trả lời trước khi chuyển đổi

Trước khi gọi `toArray`, hãy xác định kiểu mảng mà API đích cần, những loại phần tử thực tế có thể xuất hiện, và việc có cần tái sử dụng một mảng cũ hay không. Khi dùng mảng cũ, luôn nhận giá trị trả về và phân biệt độ dài vùng lưu trữ với số phần tử dữ liệu.

Sau lời gọi thành công, ô `null` ngay sau dữ liệu chỉ xuất hiện theo quy tắc mảng dư chỗ; nó không xóa mọi ô dư và không thể phân biệt độ dài bằng cách quét nếu dữ liệu vốn chứa `null`. Khi lời gọi thất bại, đừng giả định một mảng được dùng lại đã tự khôi phục.

Mô hình cần giữ là: **kiểu của đối tượng mảng quyết định giá trị nào lưu được; kích thước quyết định dùng lại hay tạo mới; số phần tử đã chép quyết định vị trí `null` kết thúc.** Ba điều này cùng giải thích hành vi chuyển đổi, thay vì dựa vào tên biến hoặc chỉ nhìn các giá trị đang in ra.
