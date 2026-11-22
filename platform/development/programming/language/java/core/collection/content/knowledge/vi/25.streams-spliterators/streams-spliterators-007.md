# Collectors.toMap: khóa trùng, hàm gộp và loại Map đích

## 1. Tạo Map là một phép quyết định cách gom dữ liệu

Giả sử một Stream đưa ra các dòng bán hàng:

~~~text
mã B, số lượng 2
mã A, số lượng 3
mã B, số lượng 5
mã C, số lượng 4
mã A, số lượng 1
~~~

Ta muốn tra cứu theo mã. Nhưng một Map chỉ giữ tối đa một giá trị cho mỗi khóa, trong khi mã `B` và `A` xuất hiện nhiều lần. Vì vậy, chuyển các dòng thành Map không chỉ là đổi cách chứa dữ liệu. Phải quyết định những dòng cùng mã được xử lý thế nào.

Một số kết quả đều có thể đúng, tùy yêu cầu:

| Quy tắc | Giá trị của B | Giá trị của A |
| --- | --- | --- |
| Giữ dòng đầu tiên | `2` | `3` |
| Giữ dòng sau cùng | `5` | `1` |
| Cộng số lượng | `7` | `4` |
| Chọn số lượng lớn nhất | `5` | `3` |
| Giữ tất cả số lượng thành danh sách | `[2, 5]` | `[3, 1]` |
| Cấm mã xuất hiện lặp | Báo lỗi | Báo lỗi |

`Collectors.toMap` cung cấp cách tạo collector để gom các phần tử vào Map. Hai hàm ánh xạ xác định khóa và giá trị; các overload khác bổ sung hàm gộp khi trùng khóa và factory tạo Map đích. [Java SE 17 — Collectors.toMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html#toMap(java.util.function.Function,java.util.function.Function)).

Bài này tập trung vào ba quyết định: **khóa được tạo ra là gì, các giá trị cùng khóa được gộp ra sao, và Map nào sẽ giữ kết quả**. Hiểu ba phần đó giúp tránh vừa mất dữ liệu vừa tưởng phép collect đã thành công đúng ý.

## 2. Đọc ba overload theo mức quyền điều khiển

Dạng viết rút gọn:

~~~java
toMap(keyMapper, valueMapper)

toMap(keyMapper, valueMapper, mergeFunction)

toMap(keyMapper, valueMapper, mergeFunction, mapFactory)
~~~

Đây là minh họa các overload, không phải những lời gọi độc lập đã có đủ biến trong phạm vi.

| Tham số | Nhiệm vụ |
| --- | --- |
| `keyMapper` | Biến một phần tử đầu vào thành khóa `K` |
| `valueMapper` | Biến phần tử đó thành giá trị `U` |
| `mergeFunction` | Nhận hai giá trị `U` cùng khóa và quyết định giá trị `U` kết quả |
| `mapFactory` | Tạo một Map mới, rỗng, phù hợp để collector chèn/gộp dữ liệu |

Với mô hình Java 17:

~~~java
record Sale(String code, int quantity) { }
~~~

có thể dùng `Sale::code` để tạo khóa và `Sale::quantity` để tạo giá trị. `quantity` là `int` nhưng được đóng gói thành `Integer` khi làm giá trị của `Map<String, Integer>`.

Phân biệt thao tác kết thúc và collector:

~~~java
Map<String, Integer> total = rows.stream().collect(
        Collectors.toMap(
                Sale::code,
                Sale::quantity,
                Integer::sum,
                LinkedHashMap::new));
~~~

`Collectors.toMap(...)` mô tả cách gom. `collect(...)` mới là thao tác kết thúc thực hiện lượt xử lý Stream. Đoạn trên giả định `rows` là danh sách các `Sale`, có các import thích hợp; chương trình đầy đủ phía sau cung cấp toàn bộ phần cần chạy.

## 3. Dạng hai tham số: cấm khóa trùng

~~~java
Map<String, Integer> byCode = rows.stream()
        .collect(Collectors.toMap(Sale::code, Sale::quantity));
~~~

Dạng này phù hợp khi mỗi khóa sau ánh xạ phải xuất hiện duy nhất. Nếu có hai đầu vào tạo ra cùng khóa, collector ném `IllegalStateException`. Nó không mặc định giữ đầu, giữ cuối hoặc cộng.

### 3.1. Giá trị bằng nhau vẫn là trùng khóa

Hai dòng `A=1` và `A=1` vẫn là hai đầu vào cùng khóa. Không có quy tắc mặc định “nếu giá trị bằng nhau thì chấp nhận”.

Nếu ứng dụng thật sự muốn chấp nhận hai bản ghi tương đương nhưng báo lỗi khi nội dung khác, cần viết một hàm gộp diễn tả chính sách đó. Không thể suy ra chính sách từ việc dùng overload hai tham số.

### 3.2. Trùng xét trên khóa sau keyMapper

Các chuỗi nguồn có thể khác nhau:

~~~text
"Java"
" java "
"JAVA"
~~~

Nhưng `trim().toLowerCase(Locale.ROOT)` tạo cùng khóa `java`. Trùng xuất hiện ở **kết quả ánh xạ khóa**, không nhất thiết ở đối tượng đầu vào trước đó.

Chính sách chuẩn hóa phải được áp dụng nhất quán. Nếu khóa biểu diễn một mã không phân biệt hoa thường, có thể chuẩn hóa mã theo quy tắc đã chọn rồi xử lý trùng trên dạng chuẩn. Không tùy tiện bỏ khoảng trắng hoặc đổi chữ hoa/thường nếu dữ liệu nghiệp vụ coi những khác biệt đó là có ý nghĩa.

### 3.3. distinct trên dòng chưa chắc làm khóa duy nhất

Với `record Sale(String code, int quantity)`, `Sale("B", 2)` và `Sale("B", 5)` là hai dòng khác nhau. `rows.stream().distinct()` không loại một trong hai chỉ vì cùng mã.

Sau đó `toMap(Sale::code, Sale::quantity)` vẫn gặp trùng khóa `B`. Phải phân biệt quan hệ bằng nhau của toàn bộ đầu vào với quan hệ bằng nhau của khóa dùng cho Map.

Tương tự, hai khóa có cùng `hashCode` chưa đủ để kết luận là cùng khóa theo equals. Xung đột giá trị băm và trùng khóa sau ánh xạ là hai chuyện khác nhau.

## 4. Hàm gộp quyết định dữ liệu nào còn lại

Dạng ba hoặc bốn tham số nhận một `BinaryOperator<U>`. Hai toán hạng và kết quả đều thuộc kiểu giá trị `U`, không phải tự động là hai phần tử đầu vào ban đầu. [Java SE 17 — BinaryOperator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/BinaryOperator.html).

Trong lượt tuần tự, khi gặp một khóa đã có giá trị, có thể hình dung:

~~~text
giá trị đang tích lũy + giá trị từ dòng mới -> giá trị thay thế
~~~

Nếu đang cộng nhiều dòng, “giá trị đang tích lũy” có thể đã là tổng của nhiều dòng trước, không còn là số lượng của một dòng đơn lẻ.

### 4.1. Giữ đầu hoặc giữ cuối là hai chính sách khác nhau

~~~java
(oldValue, newValue) -> oldValue
~~~

Giữ giá trị đã có. Với nguồn có thứ tự xử lý tuần tự, `B` giữ `2`, `A` giữ `3`.

~~~java
(oldValue, newValue) -> newValue
~~~

Giữ giá trị đến sau. Với nguồn ấy, `B` thành `5`, `A` thành `1`.

“Sau” ở đây là sau trong thứ tự xử lý được yêu cầu, không tự có nghĩa mới nhất theo thời gian nghiệp vụ. Nếu cần bản ghi có timestamp mới nhất, hãy so timestamp bằng một quy tắc tường minh; đừng dùng vị trí sau của một nguồn không có thứ tự được cam kết để suy ra độ mới.

Cũng không có bảo đảm rằng “giữ cũ” làm `valueMapper` của dòng mới được bỏ qua. Mỗi dòng vẫn phải được ánh xạ để tạo giá trị trước khi giải quyết xung đột; một phép ánh xạ sai hoặc tạo null vẫn có thể làm collect thất bại.

### 4.2. Cộng hoặc chọn lớn nhất

Các hàm phổ biến với giá trị `Integer`:

~~~java
Integer::sum
Integer::max
~~~

Với dữ liệu ban đầu:

~~~text
cộng:         B=7, A=4, C=4
chọn lớn:     B=5, A=3, C=4
~~~

Chọn quy tắc phải theo nghĩa dữ liệu. Cộng phù hợp số lượng của nhiều giao dịch; không nhất thiết phù hợp một mã trạng thái hoặc một số đo chỉ nên giữ phiên bản cuối.

Nếu tổng có thể vượt miền `int`, cần chọn mô hình số thích hợp và quy tắc kiểm tra giới hạn. Chọn `Integer::sum` không tự cung cấp kiểm tra tràn theo nhu cầu nghiệp vụ.

### 4.3. Giữ cả đối tượng bằng Function.identity

Nếu cần Map trỏ tới dòng bán hàng được chọn:

~~~java
Map<String, Sale> best = rows.stream().collect(
        Collectors.toMap(
                Sale::code,
                Function.identity(),
                BinaryOperator.maxBy(Comparator.comparingInt(Sale::quantity)),
                LinkedHashMap::new));
~~~

Lúc này kiểu giá trị là `Sale` nên hàm gộp nhận hai `Sale`. `Function.identity()` giữ chính đối tượng đầu vào làm giá trị; nó không sao chép đối tượng.

Nếu hai dòng bằng nhau theo tiêu chí số lượng nhưng khác các trường khác, cần thêm quy tắc phá hòa phù hợp. Không nên để việc chọn một trong hai chỉ là hệ quả vô tình của thứ tự duyệt.

## 5. Muốn giữ mọi dòng thì đừng âm thầm bỏ chúng

Nếu cần giữ `B -> [2, 5]`, `A -> [3, 1]` và `C -> [4]`, bài toán là phân nhóm nhiều giá trị cho mỗi khóa:

~~~java
Map<String, List<Integer>> all = rows.stream().collect(
        Collectors.groupingBy(
                Sale::code,
                LinkedHashMap::new,
                Collectors.mapping(Sale::quantity, Collectors.toList())));
~~~

Đây là lựa chọn tự nhiên hơn việc thêm một hàm “giữ đầu” chỉ để dập lỗi trùng khóa.

Có thể dùng `toMap` với giá trị là danh sách, nhưng khi đó phải tự quyết định cách tạo danh sách mới và cách gộp chúng, tránh sửa một danh sách bất biến hoặc dùng chung danh sách sai phạm vi. Với yêu cầu giữ tất cả, `groupingBy` diễn tả ý định rõ ràng hơn.

Điểm cần giữ là: **hàm gộp có thể làm mất thông tin có chủ đích**. Nếu hai giao dịch được gộp thành một tổng, không thể từ tổng đó lấy lại chính xác từng giao dịch ban đầu. Nếu chỉ giữ dòng đầu, những dòng sau không còn trong Map kết quả.

Trước khi chọn merger, hãy trả lời Map sẽ phục vụ tra cứu một đại diện, tính toán tổng hợp hay lưu toàn bộ nhóm dữ liệu. Đó là quyết định mô hình, không chỉ là một lambda ngắn cho mã biên dịch được.

## 6. Hàm gộp và xử lý song song: cần tính kết hợp

Collector có thể tích lũy từng phần dữ liệu vào các Map riêng rồi gộp các kết quả từng phần. Vì vậy, hàm gộp không chỉ được dùng như “giá trị cũ của một dòng và giá trị của dòng kế tiếp”; nó có thể nhận những giá trị đã được tổng hợp.

Hợp đồng Collector yêu cầu các phép tích lũy và kết hợp đáp ứng điều kiện để việc chia rồi ghép cho kết quả tương đương. [Java SE 17 — Collector](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collector.html).

Một điều kiện quan trọng cho quy tắc gộp là tính kết hợp:

~~~text
merge(merge(a, b), c) tương đương merge(a, merge(b, c))
~~~

Phép trừ không thỏa:

~~~text
(10 - 3) - 2 = 5
10 - (3 - 2) = 9
~~~

Nếu dùng `(a, b) -> a - b` rồi kỳ vọng luôn như một vòng lặp trừ từ trái sang phải, việc chuyển sang pipeline song song có thể làm lộ sai giả định.

Tính kết hợp không đồng nghĩa tính giao hoán. Quy tắc giữ đầu hoặc giữ cuối có tính chất theo thứ tự riêng; nó không cho phép đảo tùy ý các giá trị hoặc bỏ yêu cầu thứ tự. Nếu đầu vào không có thứ tự được cam kết hoặc dùng một phép gom unordered, “đầu/cuối” phải được đánh giá lại.

Các hàm ánh xạ và hàm gộp cũng không nên sửa nguồn Stream hoặc phụ thuộc vào một bộ đếm ngoài để quyết định kết quả. Trong pipeline song song, trạng thái dùng chung có thể tạo tranh chấp; ngay cả khi chạy tuần tự, nó làm quy tắc gộp khó hiểu và khó kiểm tra.

Với yêu cầu nghiệp vụ đặc biệt vốn là một chuỗi cập nhật có trạng thái không kết hợp được, một vòng lặp tuần tự tường minh có thể là cách diễn tả đúng hơn cố ép vào một phép gom tổng quát.

## 7. Hàm gộp trả null có nghĩa là xóa ánh xạ

Các overload có merger dùng ngữ nghĩa gộp theo `Map.merge`. Nếu hàm gộp trả `null`, ánh xạ hiện có bị xóa; không phải khóa được giữ với một giá trị null. [Java SE 17 — Map.merge](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#merge(K,V,java.util.function.BiFunction)).

Ví dụ cố ý chạy tuần tự với merger `(a, b) -> null`:

~~~text
A=10  -> {A=10}
B=1   -> {A=10, B=1}
A=20  -> gộp A trả null, xóa A -> {B=1}
A=30  -> A chưa có, thêm lại  -> {B=1, A=30}
~~~

Kết quả không phải `{A=null, B=1}`. Khóa `A` còn có thể xuất hiện trở lại nếu một dòng sau cùng khóa được xử lý sau khi ánh xạ đã bị xóa.

Đây là một hành vi cần biết để đọc API, không phải chính sách mặc định nên dùng để tránh lỗi trùng. Quy tắc xóa khi va chạm còn có thể không phù hợp các điều kiện kết hợp khi chạy song song. Ca thử trong bài chỉ minh họa chuỗi thao tác tuần tự đã nêu.

Nếu ý định là báo lỗi khi trùng, hãy ném lỗi hoặc dùng overload cấm trùng. Nếu ý định là bỏ một số dòng, cân nhắc lọc với điều kiện rõ ràng trước khi gom. Đừng trả null từ merger chỉ vì chưa quyết định phải giữ giá trị nào.

## 8. Map đích quyết định thứ tự và một phần ngữ nghĩa khóa

### 8.1. Không có factory thì không hứa một lớp Map cụ thể

Hai overload đầu trả `Map` theo hợp đồng, không bảo đảm loại triển khai, quyền sửa, tính tuần tự hóa hay tính an toàn đa luồng cụ thể. Không dựa vào một lần thấy `HashMap` trong trình gỡ lỗi để ép kiểu hoặc suy ra thứ tự đầu ra.

Nếu chỉ cần đọc và tra cứu mà không cần một hợp đồng đặc biệt, có thể giữ kết quả ở kiểu `Map<K, V>`. Nếu thứ tự, comparator hoặc khả năng sửa là một phần của yêu cầu, chỉ định đích phù hợp bằng overload bốn tham số.

### 8.2. LinkedHashMap: giữ thứ tự chèn của khóa

~~~java
Map<String, Integer> total = rows.stream().collect(
        Collectors.toMap(
                Sale::code,
                Sale::quantity,
                Integer::sum,
                LinkedHashMap::new));
~~~

Trong ví dụ với List có thứ tự và pipeline tuần tự, khóa xuất hiện lần đầu theo `B, A, C`. Các lần gộp cập nhật `B` hoặc `A` không đưa chúng xuống cuối trong LinkedHashMap chế độ thứ tự chèn mặc định.

Kết quả được in là `{B=7, A=4, C=4}`. Đây là **thứ tự khóa được chèn**, không phải thứ tự tăng dần và cũng không phải thứ tự của lần cập nhật cuối. [Java SE 17 — LinkedHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashMap.html).

Chọn LinkedHashMap không tự làm một nguồn unordered trở thành có thứ tự nghiệp vụ ổn định. Nếu nguồn không cam kết phần tử nào đến trước, cần xác định hoặc sắp xếp đầu vào trước theo yêu cầu.

### 8.3. TreeMap: sắp xếp theo khóa

~~~java
Map<String, Integer> total = rows.stream().collect(
        Collectors.toMap(
                Sale::code,
                Sale::quantity,
                Integer::sum,
                TreeMap::new));
~~~

Với khóa chuỗi thông thường, kết quả theo thứ tự tự nhiên là `{A=4, B=7, C=4}`. Nếu có comparator riêng, thứ tự khóa và việc nhận biết khóa tương đương theo comparator phụ thuộc comparator ấy. [Java SE 17 — TreeMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeMap.html).

TreeMap không sắp xếp theo giá trị. Nếu muốn tổng số lượng giảm dần, cần một bước sắp xếp các cặp theo giá trị rồi xây dựng biểu diễn kết quả phù hợp; đổi factory sang TreeMap chưa giải quyết yêu cầu đó.

### 8.4. Factory phải tạo Map mới, rỗng và dùng được cho quá trình gom

Không viết một supplier luôn trả lại cùng một Map bên ngoài đã chứa dữ liệu rồi mong collector tự phân biệt dữ liệu cũ/mới. Đặc biệt khi chia việc song song, các vùng tích lũy phải có phạm vi sở hữu phù hợp.

`LinkedHashMap::new` và `TreeMap::new` diễn tả rõ việc tạo mới. Với loại khóa enum, có thể chọn một factory tạo `EnumMap` theo đúng lớp enum nếu đó là hợp đồng đích cần có.

Một Map không hỗ trợ chèn/gộp không thể làm nơi tích lũy bình thường chỉ vì nó rỗng lúc ban đầu. Khả năng tạo đối tượng đích và khả năng thực hiện các phép tích lũy cần cùng phù hợp.

## 9. Đổi Map đích có thể đổi cách nhận biết cùng khóa

Với Map thông thường tuân thủ equals, `"a"` và `"A"` là hai khóa khác nhau. Nhưng TreeMap dùng comparator `String.CASE_INSENSITIVE_ORDER` coi chúng bằng nhau về so sánh.

Ca minh họa:

~~~java
Map<String, Integer> counts = letters.stream().collect(
        Collectors.toMap(
                Function.identity(),
                text -> 1,
                Integer::sum,
                () -> new TreeMap<>(String.CASE_INSENSITIVE_ORDER)));
~~~

Với `letters = ["a", "A", "b"]`, chương trình cho `{a=2, b=1}`. Cùng dữ liệu vào LinkedHashMap cho ba khóa `a`, `A` và `b` riêng.

Ví dụ này cố ý cho thấy tác động của comparator. Comparator không phân biệt hoa thường không nhất quán với equals của String; TreeMap vẫn có hành vi so sánh được định nghĩa, nhưng không tuân thủ đầy đủ hợp đồng Map theo equals trong trường hợp đó.

Nếu nghiệp vụ coi hai dạng mã là một, thường nên chuẩn hóa khóa thành một biểu diễn chung và dùng quy tắc khóa nhất quán, thay vì vô tình đưa một comparator làm thay đổi quan hệ khóa vào factory.

Không chỉ kiểm tra “các đối tượng khóa có khác nhau không”. Hãy kiểm tra **Map đích dùng tiêu chí gì để coi hai khóa là cùng một vị trí tra cứu**. Đồng thời tránh sửa đối tượng khóa sau khi đưa vào Map theo cách làm thay đổi equals, hashCode hoặc thứ tự so sánh cần cho cấu trúc.

## 10. null: phân biệt giá trị ánh xạ, khóa và kết quả merger

### 10.1. valueMapper trả null không được cứu bởi Map đích cho phép null

Trong các collector được minh chứng, nếu `valueMapper` trả null, collect ném `NullPointerException`. Điều này xảy ra cả ở dạng hai tham số và ở dạng dùng LinkedHashMap cho phép lưu null bằng các phép thao tác khác.

Dạng có merger gắn với `Map.merge`, vốn nhận giá trị đầu vào khác null. Dạng không merger trong OpenJDK 17 cũng kiểm tra giá trị ánh xạ khác null khi tích lũy. [OpenJDK 17 — Collectors.java](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/java/util/stream/Collectors.java).

Do đó, không sửa lỗi bằng cách chỉ đổi `HashMap` thành `LinkedHashMap`. Phải chọn chính sách cho giá trị thiếu: báo lỗi tại biên dữ liệu, lọc dòng, dùng một đối tượng biểu diễn vắng mặt hoặc một mô hình thu thập khác nếu thật sự cần ánh xạ null.

Nếu báo lỗi, có thể kiểm tra tường minh với `Objects.requireNonNull` kèm thông tin phù hợp, thay vì chờ một thông báo ít ngữ cảnh ở sâu trong phép collect. [Java SE 17 — Objects.requireNonNull](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html#requireNonNull(T)).

### 10.2. Khóa null còn phụ thuộc Map và quy tắc đích

Ví dụ dùng factory tường minh `LinkedHashMap::new` có thể lưu một khóa null với giá trị khác null. TreeMap dùng thứ tự tự nhiên không chấp nhận khóa null trong ca thử.

Không biến hành vi của một Map cụ thể thành lời hứa rằng mọi overload hoặc mọi factory đều chấp nhận khóa null. Nếu khóa thiếu là dữ liệu không hợp lệ của ứng dụng, hãy xác thực trước; chọn một Map tình cờ chấp nhận null không làm mã nghiệp vụ trở nên đúng.

### 10.3. Merger trả null là một hành vi khác

Tóm tắt ba trường hợp:

| Tình huống | Ý nghĩa |
| --- | --- |
| `valueMapper` trả null trong các ca collector đã nêu | Không có giá trị đầu vào hợp lệ để tích lũy; gây lỗi |
| Khóa ánh xạ là null | Cần xem hợp đồng Map đích và chính sách ứng dụng |
| `mergeFunction` trả null | Xóa ánh xạ theo Map.merge |

Đừng dùng một câu chung “toMap không xử lý null” rồi bỏ qua sự khác nhau. Những vị trí null này xuất hiện ở những giai đoạn và mang ý nghĩa khác nhau.

## 11. Loại Map kết quả không quyết định collector có concurrent hay không

`toMap` là collector không concurrent. Nó vẫn có thể dùng trong một pipeline song song: thư viện tạo các vùng tích lũy riêng, sau đó gộp Map từng phần theo hợp đồng. Việc ghép khóa từ nhiều Map có thể tốn chi phí.

Chỉ định một loại Map có hỗ trợ truy cập đồng thời trong factory không tự biến collector `toMap` thành collector có đặc tính CONCURRENT. Nếu cần mô hình gom đồng thời phù hợp, xem `toConcurrentMap` và hợp đồng unordered của nó.

Đừng dùng `(a, b) -> b` với một phép gom unordered rồi gọi giá trị được giữ là “dòng cuối trong tệp” khi không có cơ chế bảo toàn thứ tự đó. Tính an toàn truy cập và thứ tự nghiệp vụ là hai yêu cầu độc lập.

Ví dụ song song trong chương trình dùng phép cộng số lượng, so sánh Map kết quả theo equals với kết quả tuần tự. Nó không in thứ tự của Map mặc định hoặc đo tốc độ để suy ra một cách thực hiện luôn tốt hơn.

Ngoài Map tích lũy, chính nguồn và các đối tượng được giữ làm giá trị cũng phải phù hợp với cách truy cập. `Function.identity` không tự biến các đối tượng giá trị thành an toàn đa luồng hoặc tạo bản sao sâu.

## 12. Lỗi không phải một giao dịch quay lui toàn bộ công việc

Nếu gặp trùng khóa bị cấm, lỗi ánh xạ hoặc ngoại lệ trong merger, collect thất bại và không có Map kết quả thành công để trả về cho lời gọi ấy.

Nhưng mọi tác dụng phụ bên ngoài mà lambda đã làm trước đó không tự được hoàn tác. Ví dụ ghi một bản tin ở `valueMapper` rồi gặp khóa trùng sau đó không khiến bản tin đã ghi biến mất.

Vì vậy, các hàm nên tập trung vào biến đổi và gộp dữ liệu. Nếu cần kiểm tra dữ liệu trước một hành động bên ngoài không thể dễ hoàn tác, hãy thu và xác thực kết quả trước, sau đó mới thực hiện hành động theo một giai đoạn phù hợp.

Không đưa một Map bên ngoài dùng chung vào supplier để quan sát “kết quả dở dang” như một cơ chế lỗi mặc định. Supplier của collector phải giữ đúng hợp đồng vùng tích lũy; cần thiết kế báo lỗi có cấu trúc riêng nếu ứng dụng muốn báo tất cả mã trùng hoặc tất cả dòng sai.

## 13. Chương trình minh chứng đầy đủ

Lưu mã sau thành **ToMapPoliciesDemo.java**. Chương trình dùng record và thư viện chuẩn, tương thích Java 17.

Các Map có stdout phụ thuộc thứ tự được tạo bằng LinkedHashMap hoặc TreeMap. Ở ca dạng hai tham số, chương trình tạo một TreeMap riêng chỉ để in dữ liệu theo thứ tự; bước hiển thị đó không phải tuyên bố collector mặc định trả TreeMap.

Hàm `rejects` chỉ chấp nhận đúng họ ngoại lệ dự kiến. Ca merger trả null được chạy tuần tự có chủ đích để quan sát xóa rồi thêm lại ánh xạ. Comparator không phân biệt hoa thường là ví dụ về thay đổi tiêu chí khóa, không phải khuyến nghị bỏ qua yêu cầu nhất quán với equals.

~~~java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.TreeMap;
import java.util.function.BinaryOperator;
import java.util.function.Function;
import java.util.stream.Collectors;

public class ToMapPoliciesDemo {
    record Sale(String code, int quantity) { }
    record Label(String code, String text) { }

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
        List<Sale> rows = List.of(
                new Sale("B", 2), new Sale("A", 3),
                new Sale("B", 5), new Sale("C", 4), new Sale("A", 1));

        Map<String, Integer> unique = rows.subList(0, 2).stream()
                .collect(Collectors.toMap(Sale::code, Sale::quantity));
        System.out.println("unique-sorted-for-display=" + new TreeMap<>(unique));
        rejects("duplicate-key", IllegalStateException.class,
                () -> rows.stream().collect(Collectors.toMap(Sale::code, Sale::quantity)));
        rejects("equal-values-still-duplicate", IllegalStateException.class,
                () -> List.of(new Sale("A", 1), new Sale("A", 1)).stream()
                        .collect(Collectors.toMap(Sale::code, Sale::quantity)));
        rejects("distinct-rows-not-distinct-keys", IllegalStateException.class,
                () -> rows.stream().distinct()
                        .collect(Collectors.toMap(Sale::code, Sale::quantity)));

        Map<String, Integer> first = rows.stream().collect(Collectors.toMap(
                Sale::code, Sale::quantity, (oldValue, newValue) -> oldValue, LinkedHashMap::new));
        Map<String, Integer> last = rows.stream().collect(Collectors.toMap(
                Sale::code, Sale::quantity, (oldValue, newValue) -> newValue, LinkedHashMap::new));
        Map<String, Integer> total = rows.stream().collect(Collectors.toMap(
                Sale::code, Sale::quantity, Integer::sum, LinkedHashMap::new));
        Map<String, Integer> largest = rows.stream().collect(Collectors.toMap(
                Sale::code, Sale::quantity, Integer::max, LinkedHashMap::new));
        System.out.println("first=" + first);
        System.out.println("last=" + last);
        System.out.println("total=" + total);
        System.out.println("largest=" + largest);
        System.out.println("insertion-order=" + new ArrayList<>(total.keySet()));

        Map<String, Integer> sorted = rows.stream().collect(Collectors.toMap(
                Sale::code, Sale::quantity, Integer::sum, TreeMap::new));
        System.out.println("tree-order=" + sorted);

        Map<String, Sale> bestRows = rows.stream().collect(Collectors.toMap(
                Sale::code, Function.identity(),
                BinaryOperator.maxBy(Comparator.comparingInt(Sale::quantity)),
                LinkedHashMap::new));
        System.out.println("best-B=" + bestRows.get("B").quantity());

        Map<String, List<Integer>> all = rows.stream().collect(Collectors.groupingBy(
                Sale::code, LinkedHashMap::new,
                Collectors.mapping(Sale::quantity, Collectors.toList())));
        System.out.println("all-values=" + all);

        List<String> spellings = List.of("Java", " java ", "JAVA");
        Map<String, Integer> normalized = spellings.stream().collect(Collectors.toMap(
                text -> text.trim().toLowerCase(Locale.ROOT),
                text -> 1, Integer::sum, LinkedHashMap::new));
        System.out.println("normalized=" + normalized);

        List<String> letters = List.of("a", "A", "b");
        Map<String, Integer> ordinary = letters.stream().collect(Collectors.toMap(
                Function.identity(), text -> 1, Integer::sum, LinkedHashMap::new));
        Map<String, Integer> ignoreCase = letters.stream().collect(Collectors.toMap(
                Function.identity(), text -> 1, Integer::sum,
                () -> new TreeMap<>(String.CASE_INSENSITIVE_ORDER)));
        System.out.println("ordinary-keys=" + ordinary);
        System.out.println("comparator-keys=" + ignoreCase);

        List<Label> nullable = List.of(new Label("A", "ok"), new Label("B", null));
        rejects("null-value-two-arguments", NullPointerException.class,
                () -> nullable.stream().collect(Collectors.toMap(Label::code, Label::text)));
        rejects("null-value-linked-map", NullPointerException.class,
                () -> nullable.stream().collect(Collectors.toMap(
                        Label::code, Label::text, (a, b) -> b, LinkedHashMap::new)));

        List<Label> nullKey = List.of(new Label(null, "unknown"));
        Map<String, String> explicitNullKey = nullKey.stream().collect(Collectors.toMap(
                Label::code, Label::text, (a, b) -> b, LinkedHashMap::new));
        System.out.println("explicit-null-key=" + explicitNullKey);
        rejects("null-key-natural-tree", NullPointerException.class,
                () -> nullKey.stream().collect(Collectors.toMap(
                        Label::code, Label::text, (a, b) -> b, TreeMap::new)));

        List<Sale> cancellation = List.of(
                new Sale("A", 10), new Sale("B", 1),
                new Sale("A", 20), new Sale("A", 30));
        Map<String, Integer> removedOnMerge = cancellation.stream().collect(Collectors.toMap(
                Sale::code, Sale::quantity, (a, b) -> null, LinkedHashMap::new));
        System.out.println("null-merge-result=" + removedOnMerge);

        int left = (10 - 3) - 2;
        int right = 10 - (3 - 2);
        System.out.println("subtraction-grouping=" + left + " / " + right);
        Map<String, Integer> parallelTotal = rows.parallelStream().collect(Collectors.toMap(
                Sale::code, Sale::quantity, Integer::sum));
        System.out.println("parallel-equal=" + parallelTotal.equals(total));
        System.out.println("input-size=" + rows.size());
    }
}
~~~

Biên dịch và chạy:

~~~shell
javac --release 17 -encoding UTF-8 ToMapPoliciesDemo.java
java ToMapPoliciesDemo
~~~

Stdout chính xác:

~~~text
unique-sorted-for-display={A=3, B=2}
duplicate-key -> IllegalStateException
equal-values-still-duplicate -> IllegalStateException
distinct-rows-not-distinct-keys -> IllegalStateException
first={B=2, A=3, C=4}
last={B=5, A=1, C=4}
total={B=7, A=4, C=4}
largest={B=5, A=3, C=4}
insertion-order=[B, A, C]
tree-order={A=4, B=7, C=4}
best-B=5
all-values={B=[2, 5], A=[3, 1], C=[4]}
normalized={java=3}
ordinary-keys={a=1, A=1, b=1}
comparator-keys={a=2, b=1}
null-value-two-arguments -> NullPointerException
null-value-linked-map -> NullPointerException
explicit-null-key={null=unknown}
null-key-natural-tree -> NullPointerException
null-merge-result={B=1, A=30}
subtraction-grouping=5 / 9
parallel-equal=true
input-size=5
~~~

Mã đã biên dịch với `--release 17` và chạy trên JDK 24.0.2. Cờ biên dịch xác minh mức ngôn ngữ/API Java 17; đây không phải một lần chạy bằng JVM 17.

Các nhóm kết quả cần đối chiếu:

- Ba ca trùng khóa phân biệt khóa trùng, giá trị bằng nhau và distinct trên toàn dòng.
- `first`, `last`, `total`, `largest` dùng bốn chính sách khác nhau cho cùng dữ liệu.
- `insertion-order` và `tree-order` tách thứ tự chèn khỏi thứ tự khóa.
- `best-B` giữ cả một dòng Sale được chọn, thay vì chỉ giữ số lượng.
- `all-values` bảo toàn mọi số lượng bằng phân nhóm.
- `normalized` cho thấy các chuỗi khác nhau có thể tạo cùng khóa sau chuẩn hóa.
- Hai dòng `ordinary-keys` và `comparator-keys` cho thấy Map đích có thể thay đổi cách xử lý khóa tương đương theo comparator.
- Các ca null phân biệt giá trị đầu vào bị từ chối với khả năng lưu khóa null của Map đã chọn.
- `null-merge-result` thể hiện xóa ánh xạ rồi thêm lại, không lưu giá trị null.
- `subtraction-grouping` giải thích tại sao phải xét tính kết hợp.
- `parallel-equal` kiểm tra nội dung của kết quả cộng gộp; `input-size` xác nhận danh sách nguồn vẫn có năm dòng.

## 14. Thực hành có đáp án

### Bài 1 — Cùng khóa, cùng giá trị

Hai đầu vào tạo `A=1` và `A=1`. Dạng hai tham số của toMap có tự chấp nhận vì hai giá trị bằng nhau không?

**Đáp án:** Không. Nó cấm khóa trùng và ném IllegalStateException. Nếu muốn chấp nhận các giá trị tương đương theo một quy tắc, phải diễn tả bằng merger phù hợp thay vì dựa vào mặc định.

### Bài 2 — distinct có giải quyết mã trùng không?

Hai record `Sale("B", 2)` và `Sale("B", 5)` được đưa qua distinct rồi toMap theo mã. Vì sao vẫn lỗi?

**Đáp án:** Hai record khác nhau theo toàn bộ các thành phần nên distinct không gộp chúng. keyMapper lại tạo cùng khóa B. Tính duy nhất của đầu vào và tính duy nhất của khóa sau ánh xạ là hai điều khác nhau.

### Bài 3 — Chọn đúng chính sách gộp

Cùng mã có các số lượng `2` và `5`. Muốn tổng giao dịch thì dùng giữ cuối hay cộng? Muốn giữ một dòng có số lượng lớn nhất thì valueMapper nên trả số hay cả dòng?

**Đáp án:** Tổng là `7` nên dùng phép cộng. Nếu cần các trường khác của dòng thắng, valueMapper giữ cả dòng bằng Function.identity và merger chọn đối tượng theo comparator. Chỉ giữ số `5` sẽ không giữ những trường còn lại.

### Bài 4 — LinkedHashMap có sắp theo khóa không?

Nguồn tuần tự gặp khóa B, A, B, C và gộp theo tổng. LinkedHashMap mặc định giữ thứ tự nào? Muốn khóa tăng dần dùng gì?

**Đáp án:** Thứ tự chèn lần đầu là B, A, C; cập nhật B không đưa nó xuống cuối. Muốn thứ tự khóa tự nhiên có thể chọn TreeMap. Không Map nào trong hai cách này tự sắp theo tổng giá trị.

### Bài 5 — Hàm gộp trả null

Nguồn tuần tự có A=10, A=20, A=30 và merger luôn trả null khi được gọi. Kết quả của A cuối cùng có phải null không?

**Đáp án:** Không. Dòng thứ hai làm merger trả null và xóa A. Dòng thứ ba gặp khóa chưa có nên thêm A=30 mà không phải gộp với một giá trị đang tồn tại. Hành vi này không phải cách lưu ánh xạ A tới null.

### Bài 6 — Đổi đích sang LinkedHashMap có nhận value null không?

Một valueMapper trả null. Có thể sửa lỗi chỉ bằng cách dùng LinkedHashMap::new vì LinkedHashMap cho phép null không?

**Đáp án:** Không trong các overload được minh chứng. Giá trị null vẫn không đáp ứng quá trình tích lũy của collector, đặc biệt ngữ nghĩa Map.merge yêu cầu giá trị đưa vào khác null. Cần chính sách dữ liệu thiếu rõ ràng thay vì chỉ đổi lớp Map.

### Bài 7 — Phép trừ và parallelStream

Merger là `(a, b) -> a - b`. Vì sao không thể mặc định kết quả luôn như trừ liên tiếp từ trái sang phải khi chuyển sang song song?

**Đáp án:** Phép trừ không kết hợp: `(10-3)-2` khác `10-(3-2)`. Các Map từng phần và bước gộp có thể nhóm giá trị theo cách khác. Nếu yêu cầu thật sự là cập nhật trạng thái lần lượt, chọn một mô hình tuần tự tường minh.

### Bài 8 — Đổi comparator làm các khóa gộp lại

Nguồn có chuỗi a và A, hai khóa khác nhau theo equals. Khi đích là TreeMap dùng comparator không phân biệt hoa thường, vì sao chúng có thể gộp vào cùng vị trí?

**Đáp án:** TreeMap nhận biết tương đương khóa qua comparator; comparator đó trả 0 cho hai chuỗi. Nó không nhất quán với equals của String nên cần hiểu rõ giới hạn hợp đồng Map. Nếu nghiệp vụ coi hai dạng là một mã, chuẩn hóa khóa theo quy tắc rõ ràng thường giúp mô hình nhất quán hơn.

## 15. Những quyết định cần công bố trong mã

Trước một lời gọi toMap, hãy xác định miền khóa sau chuẩn hóa, chính sách trùng, ý nghĩa giá trị và loại Map đích. Nếu khóa lặp là lỗi dữ liệu, để lỗi được bộc lộ; nếu là dữ liệu hợp lệ, chọn gộp hoặc phân nhóm phù hợp.

Sau đó xem thứ tự đầu vào, tính kết hợp của merger, null và quyền sở hữu đối tượng kết quả. Không dùng một lambda giữ đầu/cuối như cách chữa lỗi chung cho mọi dữ liệu, và không trông chờ factory tự giải quyết những yêu cầu nó không biểu diễn.

Đọc đủ keyMapper, valueMapper, mergeFunction và mapFactory giúp thấy chính xác Map kết quả sẽ giữ thông tin gì, bỏ thông tin gì và tuân theo quy tắc nào khi một khóa xuất hiện nhiều lần.
