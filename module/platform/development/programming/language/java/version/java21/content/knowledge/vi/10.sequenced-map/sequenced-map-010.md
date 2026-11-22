# Entry snapshot từ các thao tác hai đầu và khả năng cập nhật giá trị

Trong Java 21, `SequencedMap` cung cấp `firstEntry()`, `lastEntry()`, `pollFirstEntry()` và `pollLastEntry()` để đọc hoặc lấy mapping ở hai đầu encounter order. Điểm quan trọng là cả bốn phương thức đều trả về một `Map.Entry` snapshot tại thời điểm gọi. Snapshot này không phải một entry đang liên kết để cập nhật map bằng `setValue()`.

Muốn cập nhật giá trị của mapping, hãy dùng các phương thức cập nhật của map như `put()`, `replace()`, `compute()` hoặc `merge()`. Có một trường hợp khác: entry lấy trong lúc duyệt `entrySet()` hoặc `sequencedEntrySet()` có thể cập nhật map qua `setValue()` nếu implementation hỗ trợ, nhưng không nên dựa vào liên kết đó sau khi vòng lặp kết thúc.

## 1. SequencedMap và các thao tác ở hai đầu

`SequencedMap<K,V>` là một `Map<K,V>` có encounter order xác định. Thứ tự này áp dụng cho các mapping (cặp key-value), cho phép truy cập mapping đầu/cuối, thêm mapping ở hai đầu và duyệt theo thứ tự đảo ngược.

Ví dụ, với một map có thứ tự:

~~~text
first                                  last
  |                                      |
  v                                      v
[("A", 10), ("B", 20), ("C", 30), ("D", 40)]
~~~

Java 21 cung cấp các phương thức chính sau:

| Phương thức | Hành vi | Map có bị thay đổi? |
|---|---|---|
| `firstEntry()` | Trả về mapping đầu tiên | Không |
| `lastEntry()` | Trả về mapping cuối cùng | Không |
| `pollFirstEntry()` | Xóa và trả về mapping đầu tiên | Có |
| `pollLastEntry()` | Xóa và trả về mapping cuối cùng | Có |
| `putFirst(key, value)` | Thêm hoặc cập nhật mapping rồi đặt ở đầu | Có |
| `putLast(key, value)` | Thêm hoặc cập nhật mapping rồi đặt ở cuối | Có |

Bốn phương thức đọc/lấy entry trả về `null` nếu map rỗng. Hai phương thức `poll*` là optional operations: implementation không hỗ trợ xóa có thể ném `UnsupportedOperationException`.

## 2. Entry snapshot là gì?

Snapshot là một đối tượng `Map.Entry` đại diện cho key và value của mapping tại thời điểm phương thức được gọi. Nó giữ lại cặp key-value đó để caller đọc, kể cả khi map sau đó thay đổi hoặc mapping đã bị xóa.

Các phương thức `firstEntry()`, `lastEntry()`, `pollFirstEntry()` và `pollLastEntry()` đều trả về snapshot. Snapshot không hỗ trợ cập nhật mapping trong map thông qua `setValue()`.

Ví dụ với `LinkedHashMap`:

~~~java
SequencedMap<String, Integer> scores = new LinkedHashMap<>();

scores.put("An", 8);
scores.put("Bình", 9);
scores.put("Chi", 7);

Map.Entry<String, Integer> first = scores.firstEntry();

System.out.println(first.getKey());   // An
System.out.println(first.getValue()); // 8
~~~

`first` là snapshot của mapping `An -> 8`. Nếu cập nhật map sau đó:

~~~java
scores.put("An", 10);

System.out.println(scores.get("An")); // 10
System.out.println(first.getValue()); // 8
~~~

Snapshot vẫn giữ giá trị đã ghi nhận lúc gọi `firstEntry()`. Nó không tự biến thành entry mới của mapping `An -> 10`.

Gọi `setValue()` trên snapshot không phải cách cập nhật map:

~~~java
Map.Entry<String, Integer> first = scores.firstEntry();

// Không hỗ trợ cập nhật mapping của scores:
first.setValue(11); // Ném UnsupportedOperationException
~~~

Hợp đồng Java 21 quy định snapshot không hỗ trợ mutation của map qua `setValue()`. Không nên dựa vào implementation cụ thể để mong thao tác này cập nhật được map.

## 3. Phân biệt first/last với pollFirst/pollLast

Hai nhóm phương thức có điểm chung là đều trả về snapshot, nhưng khác nhau ở tác động lên map:

- `firstEntry()` và `lastEntry()` chỉ đọc mapping ở đầu hoặc cuối.
- `pollFirstEntry()` và `pollLastEntry()` xóa mapping tương ứng khỏi map rồi trả về snapshot của mapping vừa bị xóa.

Ví dụ:

~~~java
SequencedMap<String, Integer> scores = new LinkedHashMap<>();

scores.put("An", 8);
scores.put("Bình", 9);
scores.put("Chi", 7);

Map.Entry<String, Integer> removed = scores.pollFirstEntry();

System.out.println(removed);       // An=8
System.out.println(scores);        // {Bình=9, Chi=7}
System.out.println(removed.getValue()); // 8
~~~

Sau khi `pollFirstEntry()` trả về, mapping `An -> 8` đã bị loại khỏi map. Snapshot vẫn có thể được dùng để đọc key và value đã lấy ra. Gọi `removed.setValue(...)` cũng không thể thêm lại hoặc thay đổi mapping trong map.

Nếu cần đưa mapping trở lại map, hãy dùng key và value của snapshot với phương thức map phù hợp:

~~~java
scores.putFirst(removed.getKey(), removed.getValue());
~~~

Đoạn code trên thêm mapping trở lại đầu nếu implementation hỗ trợ `putFirst`. Nó là một thao tác mới trên map, không phải thao tác sửa snapshot.

## 4. Cập nhật value bằng các phương thức của Map

Để thay đổi giá trị đang gắn với một key, sử dụng API cập nhật của `Map`. Cách này có hợp đồng rõ ràng và không phụ thuộc vào việc một `Map.Entry` có đang liên kết với map hay không.

### put và replace

~~~java
SequencedMap<String, Integer> scores = new LinkedHashMap<>();

scores.put("An", 8);
scores.put("Bình", 9);

Map.Entry<String, Integer> first = scores.firstEntry();

// Cập nhật mapping theo key:
scores.put(first.getKey(), 10);

// Hoặc chỉ thay thế khi key đã tồn tại:
scores.replace(first.getKey(), 11);

System.out.println(scores.get("An")); // 11
~~~

`put(key, value)` thêm mapping nếu key chưa có hoặc thay value nếu key đã tồn tại. `replace(key, value)` chỉ thay value khi key đã có. Các phương thức này thay đổi mapping trong map; snapshot được lấy trước đó vẫn giữ dữ liệu tại thời điểm nó được tạo.

### compute và merge

Dùng `compute` khi giá trị mới phụ thuộc vào key và giá trị hiện tại:

~~~java
scores.compute("An", (key, oldValue) ->
    oldValue == null ? 1 : oldValue + 1
);
~~~

Dùng `merge` khi muốn gộp giá trị mới với giá trị hiện có:

~~~java
scores.merge("Bình", 2, Integer::sum);
~~~

### replaceAll

`replaceAll` cập nhật giá trị của các mapping theo encounter order:

~~~java
scores.replaceAll((key, value) -> value + 1);
~~~

Các thao tác này cập nhật map trực tiếp. Chúng là lựa chọn phù hợp khi mục tiêu là thay đổi value, còn các phương thức `firstEntry()` và `lastEntry()` chỉ cung cấp snapshot để đọc.

## 5. putFirst và putLast: cập nhật value kèm thay đổi vị trí

`SequencedMap` có `putFirst(key, value)` và `putLast(key, value)`. Hai phương thức này không chỉ là alias cho `put`: khi hoàn tất bình thường, mapping được chỉ định sẽ nằm ở đầu hoặc cuối encounter order.

Với các map có thứ tự chèn như `LinkedHashMap`, nếu key đã tồn tại, `putFirst` hoặc `putLast` có thể cập nhật value đồng thời di chuyển mapping đến vị trí được yêu cầu:

~~~java
SequencedMap<String, Integer> scores = new LinkedHashMap<>();

scores.put("An", 8);
scores.put("Bình", 9);
scores.put("Chi", 7);

scores.putFirst("Chi", 10);

System.out.println(scores);
// {Chi=10, An=8, Bình=9}
~~~

`Chi` được cập nhật thành `10` và chuyển lên đầu. Nếu chỉ muốn cập nhật value mà không chủ động yêu cầu vị trí đầu/cuối, dùng `put`, `replace`, `compute` hoặc `merge`.

Không phải mọi `SequencedMap` đều có thể đặt mapping ở vị trí tùy ý. Với các implementation có thứ tự được quyết định bởi comparator, chẳng hạn `TreeMap`, `putFirst` và `putLast` ném `UnsupportedOperationException` vì vị trí phải tuân theo thứ tự sắp xếp.

## 6. Entry lấy từ sequencedEntrySet có giống snapshot không?

`sequencedEntrySet()` trả về một `SequencedSet<Map.Entry<K,V>>` view của các mapping theo encounter order. View này liên kết với map: thay đổi được hỗ trợ qua view sẽ phản ánh vào map và ngược lại.

Tuy nhiên, cần phân biệt view với từng đối tượng `Map.Entry` lấy từ view.

Khi duyệt `entrySet()` hoặc `sequencedEntrySet()`, các entry nhận được có liên kết với map trong thời gian duyệt. Nếu implementation hỗ trợ `setValue()`, gọi phương thức đó trong lúc duyệt sẽ cập nhật value của mapping tương ứng:

~~~java
SequencedMap<String, Integer> scores = new LinkedHashMap<>();

scores.put("An", 8);
scores.put("Bình", 9);
scores.put("Chi", 7);

for (Map.Entry<String, Integer> entry : scores.sequencedEntrySet()) {
    if (entry.getKey().equals("Bình")) {
        entry.setValue(10);
    }
}

System.out.println(scores.get("Bình")); // 10
~~~

Ví dụ này dùng `LinkedHashMap`, implementation cho phép cập nhật value qua entry khi duyệt.

Nhưng hợp đồng của `SequencedMap` không bảo đảm mọi entry lấy từ view đều còn liên kết với map sau khi kết thúc vòng lặp. Nó cũng không quy định rằng `setValue()` trên entry lấy bằng `sequencedEntrySet().getFirst()` chắc chắn cập nhật map hay chắc chắn ném exception. Hành vi đó phụ thuộc implementation.

Vì vậy:

- Dùng `setValue()` trong lúc duyệt nếu implementation và hợp đồng của map cho phép.
- Dùng `put`, `replace`, `compute` hoặc `merge` nếu cần cập nhật map một cách rõ ràng sau khi đã lấy entry.
- Không giả định entry lấy từ `sequencedEntrySet().getFirst()` tương đương snapshot của `firstEntry()`.
- Không giữ entry từ iterator để dùng như một handle cập nhật lâu dài sau khi iterator đã kết thúc.

## 7. Snapshot là nông, không sao chép sâu object value

Snapshot của `Map.Entry` ghi nhận key và value tại thời điểm gọi. Nó không có nghĩa Java sao chép sâu object được tham chiếu bởi value.

Ví dụ map lưu một `List<String>`:

~~~java
SequencedMap<String, List<String>> groups = new LinkedHashMap<>();
List<String> members = new ArrayList<>(List.of("An", "Bình"));

groups.put("backend", members);

Map.Entry<String, List<String>> snapshot = groups.firstEntry();
~~~

Snapshot không cho phép thay mapping qua `setValue()`. Tuy nhiên, `snapshot.getValue()` vẫn tham chiếu đến chính object list đang được map lưu. Vì thế, nếu object value có thể sửa đổi:

~~~java
snapshot.getValue().add("Chi");

System.out.println(groups.get("backend")); // [An, Bình, Chi]
~~~

Map vẫn giữ cùng mapping `backend -> members`; nội dung object list đã thay đổi. Đây là thay đổi trạng thái của object value, không phải thay thế value của mapping.

Nếu cần snapshot độc lập cả nội dung value, phải tự tạo bản sao phù hợp với kiểu dữ liệu. Với object lồng nhau, sao chép nông một collection ngoài cùng chưa chắc tạo được bản sao sâu.

## 8. Cách chọn API theo mục tiêu

| Mục tiêu | Cách làm phù hợp |
|---|---|
| Đọc mapping đầu/cuối mà không xóa | `firstEntry()` / `lastEntry()` |
| Lấy và loại mapping đầu/cuối | `pollFirstEntry()` / `pollLastEntry()` |
| Cập nhật value theo key | `put()` / `replace()` |
| Tính value mới từ value hiện tại | `compute()` / `merge()` |
| Cập nhật toàn bộ mapping | `replaceAll()` |
| Cập nhật value trong lúc duyệt | `Map.Entry.setValue()` nếu implementation hỗ trợ |
| Cập nhật value đồng thời đưa mapping lên đầu/cuối | `putFirst()` / `putLast()` nếu implementation hỗ trợ |
| Đọc mapping theo encounter order dưới dạng view | `sequencedEntrySet()` |

Một quy trình an toàn khi cần cập nhật mapping ở đầu map:

~~~java
Map.Entry<String, Integer> first = scores.firstEntry();

if (first != null) {
    scores.replace(
        first.getKey(),
        first.getValue() + 1
    );
}
~~~

Ở đây `firstEntry()` chỉ dùng để đọc key và value; `replace()` mới là thao tác cập nhật mapping. Kiểm tra `null` vì map rỗng sẽ không có entry đầu tiên.

Nếu nhiều thread cùng truy cập map, không được xem cặp thao tác đọc snapshot rồi cập nhật theo key là một giao dịch nguyên tử. Cần dùng cơ chế đồng bộ hoặc implementation concurrent phù hợp với yêu cầu nhất quán của ứng dụng.

## 9. Checklist khi làm việc với Map.Entry

- [ ] Xác định entry lấy từ `firstEntry`, `lastEntry`, `pollFirstEntry` hay `pollLastEntry`.
- [ ] Xem bốn phương thức này là snapshot; không dùng `setValue()` để cập nhật map.
- [ ] Nhớ rằng `poll*Entry()` xóa mapping, còn `firstEntry()` và `lastEntry()` chỉ đọc.
- [ ] Kiểm tra `null` trước khi truy cập entry vì map rỗng trả về `null`.
- [ ] Dùng `put`, `replace`, `compute` hoặc `merge` để cập nhật value theo key.
- [ ] Chỉ dùng `setValue()` trên entry đang được duyệt khi implementation hỗ trợ.
- [ ] Không giả định entry lấy từ `sequencedEntrySet().getFirst()` có hợp đồng giống `firstEntry()`.
- [ ] Phân biệt snapshot mapping với bản sao sâu của object value.
- [ ] Chỉ dùng `putFirst`/`putLast` khi muốn thay đổi cả vị trí encounter order và implementation hỗ trợ thao tác đó.

## Tài liệu tham khảo chính thức

- [Java SE 21 API — SequencedMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedMap.html)
- [Java SE 21 API — Map.Entry](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Map.Entry.html)
- [Java SE 21 API — Map](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Map.html)
- [Java SE 21 API — LinkedHashMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/LinkedHashMap.html)
- [Java SE 21 API — TreeMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/TreeMap.html)
- [Oracle Java 21 Core Libraries — Creating Sequenced Collections, Sets, and Maps](https://docs.oracle.com/en/java/javase/21/core/creating-sequenced-collections-sets-and-maps.html)
- [JEP 431: Sequenced Collections](https://openjdk.org/jeps/431)

