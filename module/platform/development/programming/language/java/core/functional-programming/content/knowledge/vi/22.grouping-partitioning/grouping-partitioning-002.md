# Nhóm nhiều tầng và cấu trúc `Map` lồng nhau trong Java Stream

Khi dữ liệu phải được phân loại theo **nhiều tiêu chí**, Java Stream cho phép lồng `Collectors.groupingBy()` để tạo `Map` nhiều tầng. Chẳng hạn, với danh sách yêu cầu hỗ trợ, ta muốn nhóm theo **khu vực**, rồi **mức ưu tiên**, sau đó tính số lượng hoặc tổng thời gian cho từng nhóm nhỏ nhất.

Điều cần hiểu không chỉ là cú pháp: thứ tự các cấp nhóm quyết định cấu trúc dữ liệu, downstream collector quyết định kiểu giá trị ở lá, và loại `Map` ảnh hưởng đến thứ tự trình bày. Các ví dụ sử dụng Java 17+.

## 1. Từ nhóm một tầng đến hai tầng

Giả sử phần tử nguồn được mô tả bằng record:

```java
record Ticket(String region, String priority, int minutes) {}
```

Đây là khai báo kiểu minh họa, đặt trong một class hoặc ở cấp tệp Java phù hợp. `record` đã có trong Java 17.

Với một cấp nhóm:

```java
Map<String, List<Ticket>> byRegion = tickets.stream()
        .collect(Collectors.groupingBy(Ticket::region));
```

Khóa là tên khu vực và giá trị là danh sách ticket thuộc khu vực đó.

Khi cần nhóm tiếp theo mức ưu tiên:

```java
Map<String, Map<String, List<Ticket>>> grouped =
        tickets.stream().collect(Collectors.groupingBy(
                Ticket::region,
                Collectors.groupingBy(Ticket::priority)
        ));
```

Hai đoạn trên là snippet bên trong phương thức có `tickets` kiểu `List<Ticket>`, cần `java.util.List`, `java.util.Map`, `java.util.stream.Collectors`.

Kiểu kết quả được đọc từ ngoài vào trong:

```text
Map<region, Map<priority, List<Ticket>>>

North
  High -> [ticket A, ticket B]
  Low  -> [ticket C]
South
  High -> [ticket D]
  Low  -> [ticket E, ticket F]
```

`groupingBy(Ticket::region, groupingBy(Ticket::priority))` và `groupingBy(Ticket::priority, groupingBy(Ticket::region))` **không cùng hình dạng**: cách thứ nhất tra cứu khu vực trước, cách thứ hai tra cứu ưu tiên trước. Hãy chọn thứ tự theo thao tác tra cứu hoặc giao diện cần xây dựng.

## 2. Downstream collector quyết định dữ liệu của nhóm

Dạng khái quát là `Collectors.groupingBy(classifier, downstream)`:

- `classifier` biến phần tử `T` thành khóa nhóm `K`, ví dụ `Ticket::region`.
- `downstream` nhận các phần tử cùng khóa và tổng hợp thành một giá trị `D`.
- Kết quả có dạng `Map<K,D>`. Nếu downstream lại là `groupingBy`, `D` chính là một `Map` khác.

Downstream ở cấp cuối quyết định giá trị lá:

| Downstream cuối | Kiểu dữ liệu lá | Dùng khi |
| --- | --- | --- |
| `toList()` | `List<Ticket>` | Cần giữ từng bản ghi |
| `counting()` | `Long` | Cần đếm phần tử |
| `summingInt(Ticket::minutes)` | `Integer` | Cần tổng số phút |
| `averagingInt(Ticket::minutes)` | `Double` | Cần trung bình |
| `mapping(Ticket::minutes, toList())` | `List<Integer>` | Chỉ cần một thuộc tính |
| `summarizingInt(Ticket::minutes)` | `IntSummaryStatistics` | Cần count, sum, min, max, average cùng lúc |

Ví dụ, thay vì lưu danh sách ticket, ta có thể đếm:

```java
Map<String, Map<String, Long>> counts =
        tickets.stream().collect(Collectors.groupingBy(
                Ticket::region,
                Collectors.groupingBy(
                        Ticket::priority,
                        Collectors.counting()
                )
        ));
```

Đoạn này cần ngữ cảnh `Ticket`, `tickets` và import ở trên. Đặc biệt, `counting()` trả `Long`, **không phải `Integer`**.

## 3. Chương trình Java 17+ chạy đầy đủ

Để kết quả in ra có thứ tự ổn định, ví dụ sử dụng `TreeMap` ở **cả hai cấp**. Lưu thành tệp `NestedGroupingDemo.java`:

```java
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class NestedGroupingDemo {
    record Ticket(String region, String priority, int minutes) {}

    public static void main(String[] args) {
        List<Ticket> tickets = List.of(
                new Ticket("North", "High", 30),
                new Ticket("South", "Low", 10),
                new Ticket("North", "Low", 20),
                new Ticket("North", "High", 50),
                new Ticket("South", "High", 40),
                new Ticket("South", "Low", 15)
        );

        Map<String, Map<String, List<Ticket>>> grouped =
                tickets.stream().collect(Collectors.groupingBy(
                        Ticket::region,
                        TreeMap::new,
                        Collectors.groupingBy(
                                Ticket::priority,
                                TreeMap::new,
                                Collectors.toList()
                        )
                ));

        grouped.forEach((region, byPriority) ->
                byPriority.forEach((priority, members) ->
                        System.out.println(
                                region + "/" + priority + " = "
                                + members.stream()
                                        .map(Ticket::minutes)
                                        .toList()
                        )
                )
        );

        Map<String, Map<String, Integer>> totals =
                tickets.stream().collect(Collectors.groupingBy(
                        Ticket::region,
                        TreeMap::new,
                        Collectors.groupingBy(
                                Ticket::priority,
                                TreeMap::new,
                                Collectors.summingInt(Ticket::minutes)
                        )
                ));

        Map<String, Map<String, Long>> counts =
                tickets.stream().collect(Collectors.groupingBy(
                        Ticket::region,
                        TreeMap::new,
                        Collectors.groupingBy(
                                Ticket::priority,
                                TreeMap::new,
                                Collectors.counting()
                        )
                ));

        System.out.println("totals = " + totals);
        System.out.println("counts = " + counts);
    }
}
```

Chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 NestedGroupingDemo.java
java NestedGroupingDemo
```

Stdout:

```text
North/High = [30, 50]
North/Low = [20]
South/High = [40]
South/Low = [10, 15]
totals = {North={High=80, Low=20}, South={High=40, Low=25}}
counts = {North={High=2, Low=1}, South={High=1, Low=2}}
```

**Vì sao thứ tự in trên là xác định?** `TreeMap<String,...>` duyệt key theo thứ tự tự nhiên: `North` trước `South`, `High` trước `Low`. Trong các list lá, nguồn `tickets` có encounter order và pipeline tuần tự giữ thứ tự xuất hiện của bản ghi, nên `North/High` là `[30, 50]`.

Ba lần `collect` đều tạo stream mới từ danh sách. Không được tái sử dụng một `Stream` sau terminal operation.

## 4. Cách điều khiển loại `Map` ở từng cấp

Không nên dựa vào thứ tự iteration của `Map` do overload `groupingBy(classifier, downstream)` trả về. API không cam kết loại `Map` cụ thể hoặc thứ tự key.

Overload ba đối số cho phép chỉ định map factory:

```java
Collectors.groupingBy(classifier, mapFactory, downstream)
```

Trong chương trình ở trên, `TreeMap::new` xuất hiện hai lần vì muốn sắp xếp key ở cả hai cấp.

Nếu muốn duyệt các nhóm theo thứ tự **lần đầu xuất hiện**, có thể chọn `LinkedHashMap` với stream tuần tự có thứ tự:

```java
Map<String, Map<String, List<Ticket>>> insertionOrdered =
        tickets.stream().collect(Collectors.groupingBy(
                Ticket::region,
                java.util.LinkedHashMap::new,
                Collectors.groupingBy(
                        Ticket::priority,
                        java.util.LinkedHashMap::new,
                        Collectors.toList()
                )
        ));
```

Đây là snippet chạy trong `main` của `NestedGroupingDemo`. `LinkedHashMap` giữ thứ tự chèn key của chính map. Nếu chỉ cần một thứ tự nghiệp vụ riêng (ví dụ Critical → High → Low), thứ tự tự nhiên của `String` không đáp ứng: hãy dùng enum, comparator cho `TreeMap`, hoặc sắp xếp ở bước trình bày.

## 5. Lấy số liệu ở lá với `mapping` và `summarizingInt`

Nếu chỉ muốn danh sách `minutes` trong từng nhóm:

```java
Map<String, Map<String, List<Integer>>> minutesByGroup =
        tickets.stream().collect(Collectors.groupingBy(
                Ticket::region,
                Collectors.groupingBy(
                        Ticket::priority,
                        Collectors.mapping(
                                Ticket::minutes,
                                Collectors.toList()
                        )
                )
        ));
```

`mapping` biến đổi **giá trị thuộc mỗi nhóm** trước khi chuyển xuống collector ở lá. Việc gọi `tickets.stream().map(Ticket::minutes)` trước `groupingBy(Ticket::region)` sẽ làm mất đối tượng `Ticket`, nên không còn thuộc tính `region` để phân loại nữa.

Khi cần nhiều thống kê cùng lúc:

```java
Map<String, Map<String, java.util.IntSummaryStatistics>> stats =
        tickets.stream().collect(Collectors.groupingBy(
                Ticket::region,
                Collectors.groupingBy(
                        Ticket::priority,
                        Collectors.summarizingInt(Ticket::minutes)
                )
        ));

long northHighTotal = stats.get("North").get("High").getSum();
// 80L
```

Hai đoạn là snippet trong class có `Ticket` và `tickets`. `getSum()` trên `IntSummaryStatistics` trả **`long`**, nên khai báo `long northHighTotal`, không phải `int`. Nếu nhóm có thể không tồn tại thì cần tra cứu có kiểm tra trước; xem mục 8.

## 6. Lồng ba tầng và giới hạn độ phức tạp

Khi có ba tiêu chí, có thể tiếp tục lồng downstream:

```java
Map<String, Map<String, Map<String, Long>>> threeLevels =
        tickets.stream().collect(Collectors.groupingBy(
                Ticket::region,
                Collectors.groupingBy(
                        Ticket::priority,
                        Collectors.groupingBy(
                                t -> t.minutes() >= 30 ? "Long" : "Short",
                                Collectors.counting()
                        )
                )
        ));
```

Đây là `Map<region, Map<priority, Map<durationClass, count>>>`. Ví dụ, `threeLevels.get("North").get("High").get("Long")` là `2L`.

Lồng nhiều cấp có thể phù hợp với giao diện dạng cây, nhưng số lượng kiểu generic và lệnh truy cập dài dần. Với báo cáo hai/ba chiều có mục tiêu **tra cứu tổ hợp khóa** hơn là duyệt cây, có thể dùng record làm key:

```java
record GroupKey(String region, String priority) {}

Map<GroupKey, Long> countByPair = tickets.stream()
        .collect(Collectors.groupingBy(
                t -> new GroupKey(t.region(), t.priority()),
                Collectors.counting()
        ));
```

Khai báo record `GroupKey` trong class, và đoạn collect trong phương thức có `tickets`; cần `java.util.Map`, `java.util.stream.Collectors`. Record cung cấp `equals`/`hashCode` theo các thành phần, phù hợp làm key. Kết quả `Map<GroupKey, Long>` không cần `get(region).get(priority)` mà tra cứu trực tiếp bằng `new GroupKey(region, priority)`.

## 7. Phối hợp `groupingBy` với `partitioningBy`

`groupingBy` phân loại theo các khóa do classifier sinh ra. `partitioningBy(predicate)` chia phần tử thành hai nhánh Boolean.

Nhóm khu vực trước, rồi phân vùng yêu cầu dài (`minutes >= 30`):

```java
Map<String, Map<Boolean, List<Ticket>>> byRegionAndDuration =
        tickets.stream().collect(Collectors.groupingBy(
                Ticket::region,
                Collectors.partitioningBy(t -> t.minutes() >= 30)
        ));
```

Trong nhóm `North`, nhánh `true` chứa hai ticket 30 và 50 phút, nhánh `false` chứa ticket 20 phút. `partitioningBy` tạo hai key `true` và `false`, kể cả khi một nhánh không có phần tử.

Đảo chiều:

```java
Map<Boolean, Map<String, Long>> countsByDuration =
        tickets.stream().collect(Collectors.partitioningBy(
                t -> t.minutes() >= 30,
                Collectors.groupingBy(
                        Ticket::region,
                        Collectors.counting()
                )
        ));
```

Với cách này, key ngoài là `Boolean`, còn key trong là `String region`. Hai cấu trúc khác nhau về **đường dẫn truy cập**, nên cần chọn theo nhu cầu ứng dụng.

## 8. Truy cập các nhóm có thể vắng mặt

Viết trực tiếp:

```java
List<Ticket> critical = grouped.get("West").get("Critical");
```

có thể ném `NullPointerException` nếu `"West"` không có trong map ngoài. Ngay cả khi có `"West"`, `get("Critical")` vẫn có thể trả `null`.

Tra cứu an toàn hơn:

```java
List<Ticket> critical = grouped
        .getOrDefault("West", Map.of())
        .getOrDefault("Critical", List.of());

int total = totals
        .getOrDefault("West", Map.of())
        .getOrDefault("Critical", 0);
```

Các snippet này chạy trong `main` của `NestedGroupingDemo`. `Map.of()` và `List.of()` tạo fallback bất biến, phù hợp cho **chỉ đọc**.

Tuy nhiên, dùng `0` làm fallback che đi khác biệt giữa “không có nhóm” và “nhóm có tổng thật bằng 0”. Nếu điều này có ý nghĩa nghiệp vụ, kiểm tra `containsKey` hoặc trả một kiểu biểu diễn kết quả tùy chọn.

`computeIfAbsent` có thể tạo nhóm mới trong map mutable, nên không phải thao tác đọc đơn thuần. Đừng dùng nó chỉ để đọc thống kê nếu không muốn làm thay đổi dữ liệu kết quả.

## 9. Xử lý khóa `null` và chuẩn hóa khóa

`groupingBy` không cho phép classifier trả key `null` theo hành vi chuẩn của collector: có thể xuất hiện `NullPointerException` khi nhóm dữ liệu. Với nguồn thực tế, hãy xác định chính sách xử lý giá trị thiếu.

Ví dụ quy định region thiếu được đưa vào nhóm `"UNKNOWN"`:

```java
Map<String, Long> byRegion = tickets.stream()
        .collect(Collectors.groupingBy(
                t -> t.region() == null ? "UNKNOWN" : t.region(),
                Collectors.counting()
        ));
```

Nếu dữ liệu thiếu phải gây lỗi, hãy validate trước và thông báo rõ. Không tự động xóa bản ghi chỉ để grouping chạy được.

Ngoài `null`, các chuỗi `"North"`, `"north"`, `" North "` là **ba key khác nhau**. Chỉ chuẩn hóa bằng `trim()`, `toUpperCase(Locale.ROOT)` hoặc enum nếu nghiệp vụ thật sự coi chúng cùng một nhóm. Điều này cũng ảnh hưởng đến cardinality (số khóa nhóm) và chất lượng báo cáo.

## 10. Lưu ý với parallel stream và bộ nhớ

`groupingBy` có thể được dùng với parallel stream, nhưng các kết quả trung gian phải được gộp, đôi khi làm tăng chi phí. `groupingByConcurrent` hỗ trợ concurrent collector khi ngữ nghĩa và nhu cầu xử lý phù hợp, nhưng có những giới hạn:

- Không mặc định bảo toàn encounter order của phần tử hoặc thứ tự duyệt khóa trong kết quả.
- `ConcurrentMap` không có nghĩa mọi object value trong map đều tự động an toàn nếu mã ngoài đồng thời sửa chúng.
- Nếu cần danh sách theo thứ tự đầu vào hoặc báo cáo ổn định, phải chọn chiến lược thu thập/sắp xếp rõ ràng.

Về bộ nhớ, `Map<String, Map<String, List<Ticket>>>` giữ tham chiếu đến mọi phần tử nguồn trong list ở lá. Nếu chỉ cần đếm hoặc tính tổng, dùng `counting()`/`summingInt()` thay cho `toList()` để khỏi giữ các danh sách bản ghi. Với tập dữ liệu rất lớn trong database, cân nhắc `GROUP BY` tại nguồn thay vì tải mọi hàng lên Java mới nhóm.

Hãy chọn cách tuần tự dễ hiểu trước, dùng benchmark trên dữ liệu thật nếu cân nhắc chuyển sang song song.

## 11. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Đảo vị trí `groupingBy(region, groupingBy(priority))` | Map có key ngoài/key trong khác ý nghĩa dự kiến | Xác định chiều tra cứu rồi mới chọn thứ tự nhóm |
| Chỉ viết `groupingBy(region)` nhưng muốn nhóm thêm priority | Lá vẫn là `List<Ticket>` | Lồng `groupingBy(priority)` làm downstream |
| Dùng `Map<String, Map<String, Integer>>` với downstream `counting()` | Lỗi kiểu vì `counting()` trả `Long` | Dùng `Map<String, Map<String, Long>>` |
| Gọi `get(a).get(b)` mà key `a` có thể thiếu | Nguy cơ `NullPointerException` | Kiểm tra key hoặc `getOrDefault` |
| Trông chờ `HashMap` in ra theo thứ tự cố định | Collector không bảo đảm thứ tự key | Dùng `TreeMap`, `LinkedHashMap` hoặc sắp xếp trước trình bày |
| `toMap(keyFn, valueFn)` với key trùng mà không có merge function | Có thể ném `IllegalStateException` | Dùng `groupingBy` hoặc chỉ định quy tắc merge |
| Classifier trả `null` | `groupingBy` có thể ném `NullPointerException` | Validate hoặc chuẩn hóa key thiếu theo hợp đồng |
| Nhóm quá nhiều tầng | Generic phức tạp; nhiều map con, khó duyệt | Cân nhắc record key tổng hợp hoặc DTO |
| Dùng `toList()` ở lá dù chỉ cần đếm | Giữ nhiều dữ liệu không cần thiết | Dùng downstream `counting`, `summarizingInt` |
| Nghĩ parallel `groupingByConcurrent` giữ thứ tự nguồn | Thứ tự có thể không xác định | Lựa chọn collector và thứ tự hiển thị có chủ đích |

## 12. Tự kiểm tra kiến thức

**Câu 1.** `groupingBy(Ticket::region, groupingBy(Ticket::priority))` tạo kiểu dữ liệu nào?

**Đáp án:** `Map<String, Map<String, List<Ticket>>>`, nếu cả region lẫn priority là `String`.

**Câu 2.** Muốn đếm ticket theo từng region và priority, dùng downstream cuối nào?

**Đáp án:** `Collectors.counting()`; lá là `Long`.

**Câu 3.** Muốn key cả hai tầng được sắp theo thứ tự tự nhiên, làm gì?

**Đáp án:** Dùng overload `groupingBy(classifier, TreeMap::new, downstream)` ở **cả hai cấp**.

**Câu 4.** Vì sao `grouped.get("West").get("High")` có thể lỗi?

**Đáp án:** Nếu key `"West"` không tồn tại, `get("West")` là `null`, nên gọi `.get("High")` sẽ ném `NullPointerException`.

**Câu 5.** Nếu chỉ cần thống kê hai chiều, có lựa chọn nào khác cấu trúc Map lồng nhau?

**Đáp án:** Dùng `record GroupKey(region, priority)` làm khóa cho `Map<GroupKey, Long>` và `counting()` làm downstream.

**Câu 6.** `partitioningBy` khác `groupingBy` ở điểm chính nào?

**Đáp án:** `partitioningBy` chia theo predicate thành hai key Boolean `true`/`false`, kể cả khi một nhánh rỗng; `groupingBy` tạo key theo classifier và dữ liệu nguồn.

## Ghi nhớ

- Lồng `groupingBy` trong downstream tạo cấu trúc `Map<K1, Map<K2, D>>`.
- **Vị trí classifier quyết định thứ tự cấp nhóm** và đường dẫn truy cập.
- **Downstream cuối quyết định kiểu lá:** list, count, sum, average hoặc statistics.
- Muốn thứ tự key rõ ràng, dùng overload `groupingBy(classifier, mapFactory, downstream)` ở các cấp cần thiết.
- Tra cứu nhóm vắng mặt an toàn; validate/chuẩn hóa key đầu vào.
- Khi có nhiều chiều hoặc dữ liệu lớn, cân nhắc key record tổng hợp hay phép nhóm ở nguồn dữ liệu.
