# `unordered()` và khi nào có thể bỏ ràng buộc thứ tự trong Parallel Stream (Java 8)

> **Chủ đề:** Stream song song. Bài này giải thích **encounter order** (thứ tự gặp phần tử), ý nghĩa của `BaseStream.unordered()` và cách xác định khi nào việc bỏ yêu cầu giữ thứ tự là đúng về mặt nghiệp vụ. Toàn bộ API chính được đề cập (`stream`, `parallelStream`, `unordered`, `distinct`, `limit`, `skip`, `findFirst`, `findAny`, `forEachOrdered`, `Collectors`) đã có từ Java 8 và **vẫn được hỗ trợ trên Java hiện đại**. Mã ví dụ sử dụng cú pháp Java 8, biên dịch được trên JDK 17+ với `--release 8`.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **thứ tự của nguồn**, **thứ tự gặp phần tử** và **thứ tự mà các tác vụ song song thực thi**.
2. Hiểu `unordered()` là **gỡ ràng buộc thứ tự**, không phải tráo ngẫu nhiên các phần tử hoặc chuyển thành parallel.
3. Quyết định khi nào dùng `unordered()` là **an toàn về kết quả**, đặc biệt trước `distinct()`, `limit()` và `skip()`.
4. Chọn đúng `findFirst` / `findAny`, `forEach` / `forEachOrdered` và collector phù hợp.
5. Viết bài kiểm thử không dựa vào thứ tự bất định, giữ dữ liệu đầu vào không bị can thiệp và đánh giá hiệu năng bằng đo đạc thay vì suy đoán.

## 2. Encounter order là gì?

Một stream có thể **có thứ tự gặp phần tử xác định** (ordered) hoặc **không có ràng buộc về thứ tự đó** (unordered). Đây là một thuộc tính ngữ nghĩa của pipeline, **không phải** tên một thứ tự chạy thread.

- `List` và mảng thường cung cấp stream **có encounter order**, phù hợp với thứ tự phần tử trong danh sách/mảng.
- `HashSet` không cam kết một encounter order. Không dựa vào thứ tự duyệt hiện thời của nó, dù đôi lúc log có vẻ ổn định.
- `TreeSet` có thứ tự duyệt theo comparator/thứ tự tự nhiên nên stream từ nó có thể có encounter order.
- Một số nguồn tạo stream vốn unordered; ví dụ `Stream.generate(...)` trả về stream tuần tự vô hạn, **unordered** theo hợp đồng.
- Các intermediate operation có thể giữ, áp đặt hoặc bỏ thứ tự. `map` và `filter` không tự yêu cầu đổi encounter order; `sorted` có thể áp đặt thứ tự; `unordered` bỏ yêu cầu giữ thứ tự.

Ví dụ:

```java
List<Integer> numbers = Arrays.asList(10, 20, 30, 40);

List<Integer> result = numbers.parallelStream()
        .map(n -> n / 10)
        .collect(Collectors.toList());
// result = [1, 2, 3, 4].
```

**Vì sao song song vẫn có kết quả đúng thứ tự?** Nguồn `List` có encounter order, pipeline không xóa ràng buộc đó và collector nhận kết quả đúng theo thứ tự gặp phần tử. Thời điểm từng phép `map` được thực hiện **không nhất thiết** là 10 rồi 20 rồi 30 rồi 40. Java có thể xử lý các phần tử trên nhiều worker, rồi ghép kết quả theo thứ tự ngữ nghĩa yêu cầu.

### Ba loại “thứ tự” cần tách biệt

| Khái niệm | Hỏi điều gì? | Ví dụ |
| --- | --- | --- |
| Thứ tự của dữ liệu nguồn | Nguồn có thứ tự quan sát được không? | `ArrayList` lưu `[10,20,30]`; `HashSet` không cam kết |
| Encounter order của stream | Pipeline có bắt buộc tôn trọng thứ tự logic không? | `list.stream()` có; `list.stream().unordered()` không |
| Thứ tự thực thi | Worker nào xử lý trước, lambda nào được gọi trước? | Thường **không được đảm bảo** khi chạy parallel |

Một chương trình có thể **xử lý song song nhưng trả kết quả có thứ tự**, đồng thời một stream tuần tự cũng có thể được gắn thuộc tính **unordered**. Không đồng nhất `parallel` với `unordered`.

## 3. `unordered()` thực sự làm gì?

`BaseStream.unordered()` là một **intermediate operation** trả về một stream **không phải tôn trọng encounter order**. Bạn có thể sử dụng nó trên `Stream<T>` và các primitive stream (`IntStream`, `LongStream`, `DoubleStream`). Nó không tiêu thụ stream và không tự chạy terminal operation.

```java
Stream<Integer> unordered = Arrays.asList(1, 2, 3, 4)
        .parallelStream()
        .unordered();
```

Những điều **đúng**:

- Nguồn vẫn gồm các giá trị `1,2,3,4`; `unordered()` **không lọc, thêm hay sửa phần tử**.
- Pipeline không còn bắt buộc chọn/trả phần tử theo thứ tự gốc trong các phép toán mà thứ tự có thể ảnh hưởng.
- Implementation **được phép** tận dụng khả năng bỏ thứ tự để giảm chi phí phối hợp và đồng bộ trong một số phép toán song song.
- Nếu stream vốn đã unordered, gọi `unordered()` thường không tạo thay đổi ngữ nghĩa có thể quan sát.

Những điều **sai**:

- “`unordered()` là `shuffle()`”: **Sai.** Nó không có nghĩa tráo ngẫu nhiên, không tạo một phép hoán vị mới theo hợp đồng.
- “Gọi `unordered()` là chuyển sang chạy song song”: **Sai.** `parallel()`/`parallelStream()` mới chọn chế độ song song.
- “Cứ bỏ thứ tự là chắc chắn nhanh hơn”: **Sai.** Có phép toán không được lợi đáng kể; còn có overhead song song, nguồn và collector.
- “`unordered()` sẽ cho một thứ tự ngẫu nhiên khác mỗi lần”: **Sai.** Kết quả có thể nhìn giống hệt nguồn trong nhiều lần chạy, nhưng chương trình không được dựa vào điều đó.

**Lưu ý:** `unordered()` không xóa thứ tự đã lưu trong chính `List`; nó **thay đổi hợp đồng của stream** đối với các thao tác phía sau. Tương tự, chuyển về `sequential()` **không phải** là cách phục hồi nghĩa “lấy phần tử đầu tiên của List” sau khi đã chủ động bỏ ràng buộc thứ tự.

## 4. Câu hỏi quan trọng: lúc nào được bỏ thứ tự?

Hãy tự hỏi:

> “Nếu runtime chọn hoặc xử lý các phần tử theo một thứ tự khác, **đáp án nghiệp vụ có còn hợp lệ không?**”

Nếu **có**, đặc biệt với nguồn lớn và một số phép stateful, `unordered()` có thể đáng để thử. Nếu **không**, giữ encounter order.

### 4.1. Thường có thể bỏ thứ tự

| Bài toán | Có thể bỏ? | Lý do |
| --- | --- | --- |
| Đếm tổng số bản ghi | Thường có | `count()` phụ thuộc số lượng, không phụ thuộc vị trí |
| Tính tổng số nguyên trong phạm vi không tràn | Thường có | Phép cộng số nguyên đúng phạm vi không phụ thuộc thứ tự |
| Kiểm tra có ít nhất một phần tử khớp predicate thuần | Có | `anyMatch` kiểm tra điều kiện tồn tại |
| Kiểm tra tất cả/không phần tử nào khớp | Có | `allMatch` / `noneMatch` không yêu cầu thứ tự |
| Lấy tập các giá trị khác nhau, không cần đại diện đầu tiên | Có | Có thể dùng `unordered().distinct()` |
| Chọn **bất kỳ N** phần tử hợp lệ | Có, nếu thật sự bất kỳ N | `unordered().limit(N)` không phải “N phần tử đầu” |
| Tập hợp không cần thứ tự duyệt | Có thể có | `Collectors.toSet()` không cam kết thứ tự |
| Tìm một phần tử bất kỳ thỏa điều kiện | Có thể có | `findAny` phù hợp hơn `findFirst` |
| Đếm, phân nhóm theo khóa mà không cần thứ tự các phần tử trong nhóm | Có thể có | `groupingByConcurrent` là lựa chọn để benchmark khi đúng nghiệp vụ |

### 4.2. Không nên bỏ thứ tự

- **Top-N theo thời gian/độ ưu tiên/điểm**: “N phần tử đầu” không đồng nghĩa “bất kỳ N”.
- **Trang dữ liệu (pagination)**: `skip(offset).limit(size)` yêu cầu thứ tự ổn định; phải áp dụng cách sắp xếp cụ thể trước.
- **Audit log, nhật ký giao dịch, sự kiện theo trình tự**, hoặc xuất báo cáo cần giữ đúng sequence.
- **First occurrence / last occurrence**, ví dụ tìm lỗi đầu tiên, ưu tiên sự kiện đến sớm nhất.
- **Loại trùng nhưng phải giữ bản ghi xuất hiện đầu tiên**; `distinct` trên unordered stream không bảo đảm tính ổn định này.
- **Ghép chuỗi, mã hóa thứ tự, phép gộp không giao hoán** nếu kết quả nghiệp vụ phụ thuộc thứ tự.
- **Kết quả kiểm thử/serialization** có yêu cầu trình tự lặp lại và xác định.

Quy tắc ngắn: **Không bỏ order chỉ vì thấy `parallelStream()` chạy chậm.** Trước tiên hãy xác định thứ tự có nằm trong yêu cầu đúng/sai của bài toán không.

## 5. Tác động lên `distinct()`

`distinct()` loại phần tử trùng theo `Object.equals(...)` và là **stateful intermediate operation**.

**Với ordered stream**, `distinct` phải giữ sự lựa chọn **ổn định**: trong các phần tử trùng nhau, phần tử xuất hiện đầu tiên theo encounter order được giữ. Kết quả vẫn theo encounter order.

```java
List<String> words = Arrays.asList(
        "pear", "apple", "pear", "banana", "apple", "kiwi");

List<String> orderedUnique = words.parallelStream()
        .distinct()
        .collect(Collectors.toList());
// [pear, apple, banana, kiwi]
```

**Với unordered stream**, `distinct` không cam kết giữ bản sao đầu tiên hoặc duy trì thứ tự hiển thị:

```java
Set<String> values = words.parallelStream()
        .unordered()
        .distinct()
        .collect(Collectors.toSet());

// Tập giá trị về mặt toán học: {pear, apple, banana, kiwi}.
// KHÔNG khẳng định thứ tự iterator/toString của Set.
```

Nếu các phần tử trùng theo `equals` nhưng có các field phụ **khác nhau**, việc chọn bản ghi đại diện có thể ảnh hưởng nghiệp vụ. Ví dụ hai entity có cùng mã nhưng nội dung cập nhật khác nhau: unordered `distinct` không phù hợp nếu yêu cầu **giữ bản cập nhật đầu tiên hoặc mới nhất**.

Theo JavaDoc, `distinct` trên **ordered parallel stream** có thể phải dựng barrier và buffer để giữ stability; khi không cần bảo toàn đại diện đầu tiên, `unordered()` *có thể* giúp thực thi hiệu quả hơn. **Không có mức cải thiện tốc độ cố định** trên mọi dữ liệu hoặc JVM.

**Lưu ý:** `distinct` chỉ so sánh theo `equals/hashCode` của đối tượng, không dùng comparator của `sorted` để quyết định hai phần tử trùng nhau.

## 6. Tác động lên `limit(n)` và `skip(n)`

### 6.1. `limit(n)` trên stream có thứ tự

```java
List<Integer> ids = Arrays.asList(10, 20, 30, 40, 50);

List<Integer> firstThree = ids.parallelStream()
        .limit(3)
        .collect(Collectors.toList());
// BẮT BUỘC là [10, 20, 30], vì nguồn ordered.
```

Trong parallel pipeline, để lấy **đúng ba phần tử đầu tiên**, runtime có thể cần phối hợp nhiều nhánh; với nguồn lớn, `limit` có thể đắt hơn đáng kể so với khi không có ràng buộc thứ tự.

### 6.2. `limit(n)` trên stream unordered

```java
List<Integer> anyThree = ids.parallelStream()
        .unordered()
        .limit(3)
        .collect(Collectors.toList());

// Đảm bảo có 3 phần tử từ nguồn (với nguồn hữu hạn 5 phần tử).
// Không cam kết đó phải là 10, 20, 30.
// Không cam kết một thứ tự cụ thể trong danh sách.
```

Nếu nghiệp vụ chỉ cần **bất kỳ ba bản ghi**, một tập mẫu bất kỳ, hoặc tối đa `n` phần tử để xử lý tiếp, unordered `limit` có thể phù hợp. Nếu cần “ba bản ghi đầu tiên”, “ba đơn hàng mới nhất”, “ba giá trị nhỏ nhất” thì **không**.

Nếu cần chọn chính xác theo tiêu chí, hãy đặt tiêu chí rõ ràng, ví dụ `sorted(comparator).limit(3)` (và xử lý tie-breakers). Sorting có thể tốn chi phí đáng kể; **không** thay bài toán xếp hạng bằng `unordered().limit(3)`.

### 6.3. `skip(n)` trên stream unordered

```java
List<Integer> remaining = ids.parallelStream()
        .unordered()
        .skip(2)
        .collect(Collectors.toList());

// Với nguồn 5 phần tử, còn 3 phần tử.
// Nhưng không cam kết đã bỏ đúng 10 và 20.
```

Bỏ hai phần tử **bất kỳ** là hành vi hợp lệ trong một unordered stream. Do vậy `unordered().skip(offset).limit(pageSize)` **không phù hợp cho phân trang xác định**.

Tương tự `limit`, `skip` có thể phải xử lý chi phí đồng bộ để tôn trọng encounter order trên parallel pipeline; tài liệu Java chính thức nêu rằng gỡ order có thể giúp ở trường hợp phù hợp.

### 6.4. Nguồn vô hạn và short-circuit

`limit` là **short-circuiting stateful intermediate operation**: có thể giới hạn stream vô hạn thành luồng hữu hạn, nếu pipeline/source cho phép việc thực thi kết thúc. Việc gọi `unordered()` không tự bảo đảm mọi pipeline vô hạn sẽ kết thúc; đặc biệt các phép toàn cục như `sorted()` hay một số phép `distinct()` trên nguồn vô hạn có thể khiến terminal không có kết quả.

Trên Java hiện đại có thêm `takeWhile`/`dropWhile` (từ Java 9). Với **unordered stream**, hành vi chúng có những quy tắc riêng và có thể không còn tương đương “prefix đầu danh sách”. Vì mục tiêu bài này là kiến thức Java 8, không dùng hai API đó trong mã biên dịch `--release 8`; nếu làm việc trên JDK mới, cần đọc hợp đồng API trước khi kết hợp.

## 7. `findFirst()` so với `findAny()`

Hai terminal này đều trả `Optional<T>`; đều có thể kết thúc sớm.

```java
List<String> names = Arrays.asList("alpha", "beta", "gamma");

String first = names.parallelStream()
        .findFirst()
        .orElse("missing");
// first == "alpha".

String any = names.parallelStream()
        .findAny()
        .orElse("missing");
// any là một trong "alpha", "beta", "gamma"; KHÔNG cam kết "alpha".
```

- `findFirst` tôn trọng encounter order **nếu stream có thứ tự**.
- `findAny` được phép chọn bất kỳ phần tử nào **ngay cả khi nguồn ordered**, nhằm hỗ trợ thực thi song song hiệu quả trong một số bối cảnh.
- Nếu đã gọi `unordered()`, `findFirst` **không còn nghĩa là phần tử đầu của List**; một phần tử bất kỳ có thể được trả về. Đừng viết assert kiểm tra rằng nó luôn bằng phần tử đầu tiên.

```java
String selected = names.parallelStream()
        .unordered()
        .findFirst()
        .orElse("missing");

// Chỉ kiểm tra selected thuộc nguồn nếu nguồn không rỗng.
boolean valid = names.contains(selected);
```

**Khi nào chọn API nào?**

| Yêu cầu | Chọn |
| --- | --- |
| “Tìm bản ghi đầu tiên theo thứ tự duyệt” | `findFirst` trên stream giữ ordered |
| “Tìm bất kỳ bản ghi hợp lệ nào” | `findAny` (có thể bỏ order khi an toàn) |
| “Tìm bản ghi sớm nhất theo timestamp” | Xác định comparator/tie-breaker, dùng `min` hoặc sort phù hợp |
| “Tìm phần tử bất kỳ thỏa predicate” | `filter(...).findAny()` |

**Ghi nhớ:** `findAny` không phải trình tạo số ngẫu nhiên; nó chỉ **không cam kết** chọn giá trị nào khi có nhiều ứng viên. Giá trị quan sát có thể giống nhau qua hàng ngàn lần chạy.

## 8. `forEach()`, `forEachOrdered()` và tác dụng phụ

`forEach(action)` trên parallel stream **không cam kết** thứ tự hành động; các action có thể chạy trên những thread khác nhau.

```java
List<String> names = Arrays.asList("A", "B", "C");

// Minh họa (KHÔNG có stdout cố định):
names.parallelStream().forEach(System.out::println);
```

Kết quả có thể in ra theo trình tự khác với A, B, C. Nếu yêu cầu thứ tự của log hoặc thao tác, một lựa chọn là `forEachOrdered(action)` trên **ordered stream**:

```java
names.parallelStream().forEachOrdered(System.out::println);
// In A rồi B rồi C theo encounter order.
```

Tuy nhiên, `forEachOrdered` có thể giảm mức độ song song hữu ích nếu action đòi sắp tuần tự. Tài liệu API cũng chỉ đảm bảo thứ tự của **action terminal**, chứ không khẳng định toàn bộ các bước `map/filter` trước đó chạy tuần tự. Khi dùng `forEachOrdered`, các action xảy ra theo thứ tự gặp phần tử và có quan hệ happens-before theo hợp đồng; vẫn nên tránh side effect không cần thiết ở các bước trung gian.

**Cẩn thận:** Sau `unordered()`, `forEachOrdered` không thể “khôi phục thứ tự gốc” mà stream đã từ bỏ:

```java
names.parallelStream()
        .unordered()
        .forEachOrdered(System.out::println);

// Không cam kết in A, B, C.
```

Nếu muốn **kết quả là một chuỗi có thứ tự**, thường dễ diễn đạt bằng collector khi nguồn có thứ tự:

```java
String joined = names.parallelStream()
        .collect(Collectors.joining("|"));
// "A|B|C"
```

Nếu chỉ quan tâm tập bản ghi, đừng cố ghi đồng thời vào `ArrayList` hoặc `StringBuilder` dùng chung trong `forEach` mà không có đồng bộ. Side effects và dữ liệu mutable chia sẻ có thể gây data race, sai kết quả, giảm hiệu năng. Với `collect`, hãy dùng collector đúng hợp đồng.

## 9. Ví dụ hoàn chỉnh, biên dịch và chạy được

Chương trình minh họa trực tiếp sự khác nhau giữa:

- `distinct()` giữ thứ tự trên ordered parallel stream;
- `unordered().distinct()` chỉ giữ tập giá trị, không cam kết thứ tự;
- phép tổng ký tự không phụ thuộc thứ tự;
- `unordered().limit(3)` bảo đảm số lượng chứ không hứa ba phần tử đầu;
- `findFirst()` trên ordered và unordered;
- `forEachOrdered()` giữ thứ tự logic khi nguồn ordered.

Để **stdout ổn định**, ví dụ chuyển tập unordered thành `TreeSet` **chỉ để hiển thị**, đồng thời chỉ kiểm tra membership (không in giá trị thực của `unordered().findFirst()`). Không giả tạo một thứ tự chắc chắn cho các thao tác vốn không cam kết thứ tự.

Tạo tệp **`UnorderedStreamDemo.java`**:

```java
import java.util.Arrays;
import java.util.List;
import java.util.TreeSet;
import java.util.stream.Collectors;

public class UnorderedStreamDemo {
    public static void main(String[] args) {
        List<String> words = Arrays.asList(
                "pear", "apple", "pear", "banana", "apple", "kiwi");

        // Nguồn List có encounter order: distinct giữ phần tử đầu.
        List<String> stableUnique = words.parallelStream()
                .distinct()
                .collect(Collectors.toList());

        // Bỏ yêu cầu giữ thứ tự; TreeSet chỉ dùng để in kết quả ổn định.
        TreeSet<String> unorderedUniqueForDisplay = words.parallelStream()
                .unordered()
                .distinct()
                .collect(Collectors.toCollection(TreeSet::new));

        // Tổng độ dài của các từ không phụ thuộc vào thứ tự.
        int totalCharacters = words.parallelStream()
                .unordered()
                .mapToInt(String::length)
                .sum();

        // Chỉ khẳng định số phần tử, không khẳng định chúng là từ nào.
        long anyThreeCount = words.parallelStream()
                .unordered()
                .limit(3)
                .count();

        // Nguồn ordered => findFirst lấy "pear".
        String orderedFirst = words.parallelStream()
                .findFirst()
                .orElse("missing");

        // Không hứa giá trị cụ thể sau khi bỏ encounter order.
        String unorderedFirst = words.parallelStream()
                .unordered()
                .findFirst()
                .orElse("missing");

        // forEachOrdered giữ thứ tự action của nguồn List.
        StringBuilder trace = new StringBuilder();
        words.parallelStream().forEachOrdered(s -> {
            if (trace.length() > 0) {
                trace.append("|");
            }
            trace.append(s);
        });

        System.out.println("Ordered distinct: " + stableUnique);
        System.out.println("Unordered distinct values (sorted for display): "
                + unorderedUniqueForDisplay);
        System.out.println("Character sum: " + totalCharacters);
        System.out.println("Any-three count: " + anyThreeCount);
        System.out.println("Ordered first: " + orderedFirst);
        System.out.println("Unordered first belongs to source: "
                + words.contains(unorderedFirst));
        System.out.println("forEachOrdered: " + trace);

        if (!stableUnique.equals(Arrays.asList(
                    "pear", "apple", "banana", "kiwi"))
                || !unorderedUniqueForDisplay.equals(
                    new TreeSet<String>(Arrays.asList(
                            "pear", "apple", "banana", "kiwi")))
                || totalCharacters != 28
                || anyThreeCount != 3
                || !orderedFirst.equals("pear")
                || !words.contains(unorderedFirst)
                || !trace.toString().equals(
                    "pear|apple|pear|banana|apple|kiwi")) {
            throw new AssertionError("Wrong stream result");
        }
        System.out.println("Checks passed.");
    }
}
```

Chạy bằng JDK 17+; `--release 8` kiểm soát cú pháp/API để tương thích Java 8:

```bash
javac --release 8 UnorderedStreamDemo.java
java UnorderedStreamDemo
```

**Stdout cố định theo các điều kiện của bài (đã chạy và đối chiếu trên OpenJDK 24):**

```text
Ordered distinct: [pear, apple, banana, kiwi]
Unordered distinct values (sorted for display): [apple, banana, kiwi, pear]
Character sum: 28
Any-three count: 3
Ordered first: pear
Unordered first belongs to source: true
forEachOrdered: pear|apple|pear|banana|apple|kiwi
Checks passed.
```

**Vì sao đầu ra có thể ghi cố định như trên?** Ordered `distinct` trên `List` giữ thứ tự đầu tiên. `TreeSet` áp đặt thứ tự từ điển **sau khi** `unordered().distinct()`; đó **không** phải thứ tự mà `unordered` tự tạo. `sum` cộng tổng các độ dài nguyên nhỏ trong phạm vi không tràn. `limit(3).count()` chỉ kiểm tra size. `words.contains(unorderedFirst)` xác nhận phần tử hợp lệ thay vì đoán phần tử nào sẽ được chọn. Cuối cùng `forEachOrdered` chỉ được dùng trên stream vẫn ordered.

**Điều không nên làm:** Ghi `System.out.println("Unordered first: " + unorderedFirst)` rồi đưa ra một stdout cụ thể duy nhất như đó là kết quả bắt buộc; Java không có hợp đồng như vậy.

## 10. `unordered()` và `Collectors` khi xử lý song song

### 10.1. Thu thập thành danh sách/tập

```java
List<Integer> ids = Arrays.asList(3, 1, 2, 1);

List<Integer> ordered = ids.parallelStream()
        .distinct()
        .collect(Collectors.toList());
// [3, 1, 2]

Set<Integer> asSet = ids.parallelStream()
        .unordered()
        .collect(Collectors.toSet());
// Tập giá trị {1,2,3}; không cam kết thứ tự duyệt Set.
```

Nếu cần tính đồng nhất của kết quả theo **tập giá trị**, nên kiểm tra `Set.equals(...)` hoặc so sánh sau khi chủ động sắp xếp, thay vì kiểm tra chuỗi `toString()` của một `HashSet`.

### 10.2. `groupingBy` so với `groupingByConcurrent`

`Collectors.groupingBy(classifier)` thường cho kết quả dạng `Map<K,List<T>>`, nhưng thứ tự khóa của Map mặc định không được cam kết. Trên ordered stream, thứ tự phần tử trong từng List của kết quả có thể có ý nghĩa.

`Collectors.groupingByConcurrent(classifier)` là một **concurrent và unordered collector**. Nó có thể phù hợp nếu không cần bảo toàn thứ tự phần tử trong mỗi nhóm và muốn thử concurrent reduction trên stream song song:

```java
List<String> names = Arrays.asList("a", "bb", "c", "ddd");

Map<Integer, List<String>> grouped = names.parallelStream()
        .unordered()
        .collect(Collectors.groupingByConcurrent(String::length));

// Nhóm độ dài 1 chứa {"a", "c"} theo nghĩa tập/đa tập.
// Không dựa vào thứ tự "a" rồi "c" trong List của nhóm.
```

**Quan trọng:** `groupingByConcurrent` không có nghĩa mọi tình huống đều nhanh hơn `groupingBy`. Chi phí tranh chấp khóa, phân bố dữ liệu, Map kết quả và downstream collector ảnh hưởng đáng kể. Nếu một nhóm bắt buộc giữ thứ tự theo timestamp, không thể bỏ thứ tự rồi coi List của nhóm vẫn giữ encounter order.

### 10.3. Reduction cần đúng cả thứ tự và phép toán

`reduce` song song cần phép gộp có identity và tính kết hợp thích hợp. Nếu **kết quả cần độc lập hoàn toàn với thứ tự** sau `unordered()`, cũng nên kiểm tra tính **giao hoán (commutativity)** của phép gộp hoặc những thuộc tính đảm bảo đầu ra bất biến với mọi permutation hợp lệ.

- Cộng các số nguyên trong phạm vi không tràn: associative và commutative theo ý nghĩa tổng, phù hợp để bỏ order.
- Lấy max/min theo comparator nhất quán: có thể phù hợp, nhưng cần quy tắc chọn khi nhiều phần tử bằng điểm.
- Nối chuỗi bằng `String::concat`: kết hợp theo nhóm được nhưng **không giao hoán**; `"ab"` khác `"ba"`. Nếu ghép chuỗi phải đúng thứ tự, giữ ordered.
- Cộng `double`: do sai số floating point, thứ tự cộng có thể ảnh hưởng kết quả cuối; không tự khẳng định bitwise identical khi thay đổi phép tính/phân nhóm. Với yêu cầu tài chính chính xác, dùng mô hình số phù hợp hơn.
- Phép trừ hay phép chia không thỏa tính kết hợp thông thường, không dùng làm reduction song song tự do nếu muốn kết quả ổn định.

Không đồng nhất “không cần thứ tự hiển thị Map” với “có thể bỏ encounter order trong toàn bộ thuật toán”. Xem từng bước của pipeline, nhất là phép chọn phần tử và phép gộp.

## 11. `unordered()` không phải công cụ tăng tốc mặc định

### 11.1. Vì sao *có thể* giúp?

Một số thao tác stateful có yêu cầu phối hợp lớn khi phải giữ thứ tự:

| Operation | Có encounter order | Khi bỏ order |
| --- | --- | --- |
| `distinct` | Phải giữ bản xuất hiện đầu khi trùng, có thể cần barrier/buffering | Không cần ổn định bản đại diện đầu; có thể tránh một phần chi phí |
| `limit(n)` | Phải chọn `n` phần tử đầu tiên | Được chọn `n` phần tử bất kỳ, có thể giảm phối hợp |
| `skip(n)` | Phải bỏ đúng `n` phần tử đầu tiên | Được bỏ `n` phần tử bất kỳ, có thể giảm phối hợp |
| `findFirst` | Phải tìm phần tử đầu theo thứ tự | Trên unordered stream có thể chọn phần tử bất kỳ |
| `groupingByConcurrent` | Không phù hợp nếu phải giữ thứ tự phần tử mỗi nhóm | Có thể dùng concurrent reduction khi không cần thứ tự |

Đây là **khả năng tối ưu được tài liệu API mô tả**, không phải cam kết thời gian chạy hay bộ nhớ.

### 11.2. Những trường hợp không thấy lợi ích rõ

```java
long sum = LongStream.rangeClosed(1, 1_000_000)
        .parallel()
        .unordered()
        .sum();
```

Phép tổng primitive đã có đặc tính gộp phù hợp; bỏ order không nhất thiết tạo ra thay đổi đáng kể. Một pipeline `map/filter` đơn giản có thể song song hóa hiệu quả ngay khi ordered. Trên tập dữ liệu nhỏ, chi phí chia task, quản lý worker, tạo Map/tập kết quả có thể áp đảo thời gian xử lý.

**Nguồn và tính có thứ tự:** Nếu nguồn vốn unordered, thêm `unordered()` nhiều khả năng không làm thay đổi gì hữu ích. Ngược lại, nếu nguồn ordered mà phía sau cần stable `limit` hoặc `distinct`, bỏ order có thể nhanh hơn nhưng **sai ý nghĩa**.

### 11.3. Chọn cách benchmark

Để biết có nên dùng `unordered()` trong môi trường thực:

1. **Đặt tiêu chí đúng/sai trước:** ví dụ với tập hợp các phần tử không trùng, so sánh theo Set; với `limit` bất kỳ N, kiểm tra đủ N phần tử hợp lệ thay vì kiểm tra ba phần tử đầu.
2. **Đối chiếu hai pipeline tương đương nghiệp vụ:** có và không `unordered()`; cùng tập dữ liệu, JDK, mức độ parallelism, kích thước source.
3. **Thử cả tuần tự và song song** khi cần, vì việc dùng parallel không bảo đảm có lợi.
4. **Dùng JMH** cho microbenchmark có warmup, multiple forks, chống dead-code elimination; tránh kết luận từ một lần `System.nanoTime()`.
5. **Đo end-to-end, allocation và GC**, không chỉ nanoseconds/op; khi source nhỏ hoặc tắc nghẽn I/O, lợi ích từ việc bỏ thứ tự có thể không đáng kể.
6. **Không áp dụng nếu đổi ngữ nghĩa:** kết quả nghiệp vụ sai không thể bù bằng tốc độ.

## 12. Những lỗi phổ biến và cách sửa

| Lỗi | Vì sao sai? | Cách sửa |
| --- | --- | --- |
| Nghĩ `unordered()` xáo trộn dữ liệu | API chỉ bỏ ràng buộc order, không shuffle | Dùng phép trộn có seed rõ ràng nếu thực sự cần ngẫu nhiên |
| Nghĩ `parallelStream()` đồng nghĩa unordered | Parallel là mode thực thi; encounter order là hợp đồng kết quả | Xem nguồn và các bước pipeline |
| Dùng `unordered().limit(10)` cho 10 bản ghi mới nhất | Có thể chọn bất kỳ 10 phần tử | Sắp xếp theo timestamp và tie-breaker rồi lấy 10 |
| Dùng `unordered().skip(offset)` để phân trang | Không xác định phần tử nào bị bỏ | Giữ thứ tự ổn định trước `skip/limit` |
| Dùng unordered `distinct` khi cần bản đầu tiên | Không bảo đảm chọn đại diện đầu | Giữ ordered hoặc định nghĩa tiêu chí đại diện |
| Gọi `findFirst` sau `unordered` rồi mặc định là first của List | Stream không còn encounter order bắt buộc | Giữ ordered hoặc dùng `findAny` nếu bất kỳ đều hợp lệ |
| Gọi `forEachOrdered` sau `unordered` và mong phục hồi thứ tự cũ | Không có encounter order để bắt buộc | Không bỏ order từ đầu |
| Ghi trực tiếp vào `ArrayList` chung trong `parallel().forEach` | Data race, mất/corrupt phần tử | Dùng `collect` hoặc cấu trúc concurrent đúng nghiệp vụ |
| Kiểm tra unordered output bằng `toString()` | Map/Set không hứa thứ tự duyệt | So sánh membership/Set hoặc sắp xếp để hiển thị |
| Tin unordered chắc chắn nhanh hơn | Mức cải thiện tùy operation/source/JVM | Benchmark bằng JMH và workload thật |
| Dùng `findAny` rồi viết assert giá trị đầu | `findAny` cố ý nondeterministic | Assert giá trị thuộc tập ứng viên |
| Nối chuỗi từ unordered stream và mong chuỗi có thứ tự | Phép nối phụ thuộc permutation | Duy trì ordered hoặc sắp xếp có chủ đích |

## 13. Kiểm thử đúng với chương trình unordered

Khi có đoạn `parallelStream().unordered()`, unit test nên phân biệt:

- **Các bất biến chắc chắn:** kích thước, số lượng, tập phần tử, predicate đúng trên từng phần tử, tổng số học hợp lệ.
- **Các giá trị được phép thay đổi:** thứ tự trong List, phần tử được chọn bởi `findAny` hoặc `findFirst` sau unordered, đại diện được giữ khi các object trùng theo `equals`.
- **Thứ tự chỉ được khẳng định khi đã có cam kết:** `List.stream()` giữ encounter order; `forEachOrdered` trên pipeline ordered tôn trọng nó; `sorted()` theo comparator xác định thứ tự giá trị (nếu comparator tie, cần tie-breaker cho thứ tự hoàn toàn).

Các ví dụ sau là **đoạn minh họa trong method test**, không phải file Java độc lập:

```java
List<Integer> ids = Arrays.asList(10, 20, 30, 40, 50);

List<Integer> anyThree = ids.parallelStream()
        .unordered()
        .limit(3)
        .collect(Collectors.toList());

// Tốt: kiểm tra hợp đồng, không đoán 3 phần tử cụ thể.
assert anyThree.size() == 3;
assert ids.containsAll(anyThree);

List<Integer> firstThree = ids.parallelStream()
        .limit(3)
        .collect(Collectors.toList());

// Tốt: ordered source + ordered limit bắt buộc lấy 3 đầu.
assert firstThree.equals(Arrays.asList(10, 20, 30));
```

Lưu ý Java `assert` có thể bị tắt ở runtime nếu không bật `-ea`. Trong dự án thực tế nên dùng `assertEquals`/`assertTrue` của JUnit Jupiter (JUnit 5) hoặc cơ chế assertion phù hợp; mẫu trên chỉ minh họa điều kiện cần kiểm tra. Đừng thêm vòng lặp chạy hàng nghìn lần rồi kết luận “nếu chưa thấy đổi thứ tự thì chắc chắn có order”.

### Trường hợp cần kết quả xác định sau một bước unordered

Nếu pipeline có bước đầu không cần giữ order nhưng cuối cùng cần kết quả được sắp theo một tiêu chí thật, có thể dùng `sorted(comparator)` sau đó:

```java
List<Integer> sortedValues = ids.parallelStream()
        .unordered()
        .sorted()
        .collect(Collectors.toList());
// [10, 20, 30, 40, 50]
```

Điều này tạo **thứ tự sắp xếp theo giá trị**, **không** phục hồi “thứ tự gốc” của nguồn khi thứ tự gốc khác thứ tự giá trị. `sorted` cũng là stateful operation, có thể tiêu tốn bộ nhớ và thời gian; không phải cách “miễn phí” để vừa bỏ order vừa có thứ tự.

## 14. Bài tập thực hành

1. Cho `List<Integer> ids = Arrays.asList(9, 3, 9, 1, 5)`. Viết pipeline giữ **lần xuất hiện đầu tiên** của mỗi giá trị khi loại trùng. Đáp án: `ids.parallelStream().distinct().collect(Collectors.toList())` trả `[9, 3, 1, 5]`.
2. Với danh sách trên, nếu chỉ cần tập giá trị duy nhất, có thể dùng `unordered().distinct()` không? Có, nếu không yêu cầu thứ tự/đại diện đầu và các phần tử được xét theo giá trị bằng nhau.
3. `ids.parallelStream().unordered().limit(2)` có hứa trả `[9,3]` không? Không. Khi nguồn có đủ phần tử, hai giá trị được chọn hợp lệ nhưng không nhất thiết là hai giá trị đầu.
4. Tại sao `findAny` phù hợp hơn `findFirst` cho “tìm bất kỳ bản ghi hợp lệ”? Vì không ép runtime tìm ứng viên đầu theo encounter order.
5. `ids.parallelStream().unordered().forEachOrdered(System.out::println)` có bắt buộc in `9,3,9,1,5` không? Không, vì `unordered` đã loại bỏ ràng buộc encounter order.
6. Một báo cáo yêu cầu “10 đơn hàng đầu tiên theo thời gian tạo”. Có nên gắn `unordered()` trước `limit(10)` để chạy nhanh? Không; phải có thứ tự và tie-breaker phù hợp.
7. `IntStream.range(0,1_000_000).parallel().unordered().sum()` được bảo đảm nhanh hơn cùng phép tính không có `unordered()` không? Không. Đo trên dữ liệu và JDK thực tế.
8. Vì sao `sorted()` sau `unordered()` không đơn thuần là “khôi phục thứ tự gốc”? Vì nó thiết lập thứ tự dựa trên comparator thay vì encounter order ban đầu.

## 15. Tài liệu tham khảo chính thống (API còn áp dụng)

- [Oracle Java SE 25 — `java.util.stream`, phần Ordering](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/package-summary.html): nguồn ordered/unordered, hiệu quả parallel streams, các quy tắc non-interference và collector concurrency.
- [Oracle Java SE 25 — `BaseStream.unordered()`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/BaseStream.html): hợp đồng trả về stream không có encounter order.
- [Oracle Java SE 25 — `Stream`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html): `distinct`, `limit`, `skip`, `findFirst`, `findAny`, `forEach`, `forEachOrdered` và lưu ý hiệu năng.
- [Oracle Java SE 25 — `Collectors`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Collectors.html): `groupingBy`, `groupingByConcurrent`, `toList`, `toSet` và đặc tính của collectors.
- [OpenJDK — JMH](https://github.com/openjdk/jmh): Java Microbenchmark Harness để so sánh hiệu năng có kiểm soát.

**Ghi nhớ cốt lõi:** `unordered()` là **cho phép chương trình không phải giữ encounter order**, không phải “làm dữ liệu ngẫu nhiên” hay “luôn nhanh hơn”. Chỉ dùng khi **mọi kết quả được phép chọn/duyệt theo thứ tự khác vẫn đáp ứng bài toán**, đặc biệt trước những thao tác tốn chi phí giữ thứ tự như parallel `distinct`, `limit` và `skip`. Khi “đầu tiên”, “thứ tự”, “mới nhất”, “sắp xếp” hoặc “phân trang” là một phần của yêu cầu, đừng bỏ ràng buộc đó.
