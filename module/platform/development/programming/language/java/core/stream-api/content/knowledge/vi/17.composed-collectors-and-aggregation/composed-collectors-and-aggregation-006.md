# Lọc trong từng nhóm bằng filtering

## 1. Vì sao cần lọc sau khi đã xác định nhóm?

Trong **Java Stream API**, một pipeline thường lấy dữ liệu từ nguồn, sử dụng các thao tác trung gian như `filter` và `map`, rồi kết thúc bằng `collect`, `reduce` hoặc một terminal operation khác. Khi tổng hợp báo cáo, ta hay dùng `Collectors.groupingBy` để chia các phần tử theo khóa như phòng ban, khu vực hay trạng thái.

Giả sử một hệ thống có ba nhóm công việc: **Backend**, **Frontend** và **Mobile**. Yêu cầu là báo cáo **các ticket chưa xử lý có độ ưu tiên cao của từng nhóm**, kể cả khi nhóm đó không có ticket nào đạt điều kiện.

Nếu lọc ở đầu Stream, một nhóm có dữ liệu nguồn nhưng không có ticket đạt điều kiện sẽ biến mất khỏi kết quả. Đó có thể là điều không mong muốn khi giao diện cần hiển thị cả nhóm với danh sách rỗng hoặc số đếm bằng 0.

`Collectors.filtering` giải quyết vấn đề bằng cách đặt bước lọc **bên trong một collector khác**, thường là downstream collector của `groupingBy`.

```text
                        Stream<Ticket>
                              |
                              v
                       groupingBy(team)
                          /    |     \
                      Backend Frontend Mobile
                          |      |       |
                 filtering(predicate) trong từng nhóm
                          |      |       |
                    [T01]    [T06]     []
                              |
                              v
                Map<String, List<Ticket>>
```

Điểm phân biệt then chốt:

- **`stream.filter(...).collect(groupingBy(...))`:** loại phần tử **trước khi tạo nhóm**. Nhóm không còn phần tử phù hợp sẽ **không xuất hiện**.
- **`stream.collect(groupingBy(..., filtering(..., toList())))`:** mọi phần tử nguồn vẫn được đưa qua classifier để xác định nhóm. Nhóm đã xuất hiện trong nguồn có thể được giữ lại với **danh sách rỗng** nếu tất cả phần tử của nhóm bị downstream filtering loại.

Trong chương **Collector nhiều tầng và tổng hợp**, đây là kỹ thuật quan trọng để tạo báo cáo đầy đủ danh mục, phân biệt "không có nhóm" với "nhóm có mặt nhưng không có bản ghi đạt tiêu chí".

**Mục tiêu sau bài học:** hiểu hợp đồng của `Collectors.filtering`; chọn đúng vị trí lọc; kết hợp `groupingBy`, `mapping`, `counting`, `summingInt`, `teeing`; nhận biết nhóm rỗng, `null`, thứ tự và giới hạn song song; áp dụng cho một báo cáo Java có thể chạy độc lập.

**Phiên bản Java:** `Collectors.filtering` xuất hiện từ **Java 9**. Các ví dụ sử dụng `record` và `Stream.toList()` cần Java 16+; ví dụ hoàn chỉnh chọn Java 17+.

## 2. Hợp đồng của Collectors.filtering

Chữ ký trên `java.util.stream.Collectors`:

```java
public static <T, A, R> Collector<T, ?, R> filtering(
        Predicate<? super T> predicate,
        Collector<? super T, A, R> downstream
)
```

Các thành phần:

| Thành phần | Vai trò |
| --- | --- |
| `T` | Kiểu phần tử đưa vào downstream collector. |
| `predicate` | Điều kiện quyết định phần tử có được chuyển cho downstream hay không. |
| `downstream` | Collector nhận **các phần tử đạt điều kiện** và tạo kết quả `R`. |
| `Collector<T, ?, R>` | Collector mới có thêm bước lọc trước downstream. |

Không giống `Stream.filter`, `Collectors.filtering` **không trả về Stream**. Nó trả về **một Collector** để sử dụng trong `collect` hoặc lồng bên trong collector khác.

```java
import java.util.List;
import java.util.stream.Collectors;

List<Integer> numbers = List.of(1, 2, 3, 4, 5);

List<Integer> even = numbers.stream()
        .collect(Collectors.filtering(
                n -> n % 2 == 0,
                Collectors.toList()
        ));

System.out.println(even); // [2, 4]
```

Ở dạng không có nhóm này, kết quả tương đương về nội dung với `numbers.stream().filter(n -> n % 2 == 0).toList()` trên dữ liệu minh họa. Lợi ích rõ rệt của `filtering` xuất hiện khi ta muốn **lọc trong một bước thu thập lồng nhau**.

`filtering` không tự tạo nhóm, không gộp phần tử và không bắt buộc trả về List. **Loại kết quả phụ thuộc vào downstream**: với `counting` là `Long`, với `summingInt` là `Integer`, với `maxBy` là `Optional<T>`.

## 3. Ví dụ tối thiểu: nhóm có dữ liệu nhưng không có ticket phù hợp

Tạo dữ liệu dùng chung trong các ví dụ:

```java
record Ticket(
        String id,
        String team,
        int priority,
        boolean resolved,
        int minutes
) {}

List<Ticket> tickets = List.of(
        new Ticket("T01", "Backend", 5, false, 30),
        new Ticket("T02", "Frontend", 2, false, 15),
        new Ticket("T03", "Backend", 3, true, 20),
        new Ticket("T04", "Backend", 1, false, 45),
        new Ticket("T05", "Mobile", 4, true, 10),
        new Ticket("T06", "Frontend", 4, false, 60)
);
```

Điều kiện nghiệp vụ: ticket **chưa giải quyết** và **độ ưu tiên ít nhất 4**.

### Cách A: filter trước groupingBy

```java
Map<String, List<Ticket>> filteredBeforeGrouping = tickets.stream()
        .filter(ticket -> !ticket.resolved() && ticket.priority() >= 4)
        .collect(Collectors.groupingBy(Ticket::team));

System.out.println(filteredBeforeGrouping.keySet());
// Chỉ có Backend và Frontend; thứ tự khóa không được bảo đảm.

System.out.println(filteredBeforeGrouping.containsKey("Mobile"));
// false
```

Ticket `T05` là ticket duy nhất thuộc `Mobile` nhưng đã giải quyết, nên không qua `Stream.filter`. Vì vậy classifier `Ticket::team` **không gặp** nhóm `Mobile`, và Map không có khóa đó.

### Cách B: filtering là downstream của groupingBy

```java
Map<String, List<Ticket>> filteredInsideGroups = tickets.stream()
        .collect(Collectors.groupingBy(
                Ticket::team,
                Collectors.filtering(
                        ticket -> !ticket.resolved() && ticket.priority() >= 4,
                        Collectors.toList()
                )
        ));

System.out.println(
        filteredInsideGroups.get("Backend").stream().map(Ticket::id).toList()
); // [T01]

System.out.println(
        filteredInsideGroups.get("Frontend").stream().map(Ticket::id).toList()
); // [T06]

System.out.println(filteredInsideGroups.get("Mobile")); // []
System.out.println(filteredInsideGroups.containsKey("Mobile")); // true
```

`groupingBy` đã gặp `Mobile` từ ticket `T05` và tạo một nhóm cho khóa ấy. Downstream `filtering` không chuyển `T05` cho `toList`, do đó danh sách kết quả của nhóm là rỗng.

| Trường hợp | `filter` trước `groupingBy` | `groupingBy` + downstream `filtering` |
| --- | --- | --- |
| Nhóm có phần tử đạt điều kiện | Có khóa, có phần tử | Có khóa, có phần tử |
| Nhóm có phần tử nguồn nhưng **không phần tử nào đạt** | **Không có khóa** | **Có khóa, kết quả downstream rỗng** |
| Khóa chưa từng xuất hiện ở nguồn | Không có khóa | Không có khóa |
| Nguồn rỗng hoàn toàn | Map rỗng | Map rỗng |

**Lưu ý:** `filtering` không tự sinh nhóm cho những khóa chưa từng xuất hiện. Nếu báo cáo phải hiển thị cả đội `QA` dù không có ticket đầu vào nào, cần bổ sung danh mục đội từ nguồn đáng tin cậy sau khi thu thập hoặc thiết kế dữ liệu nguồn chứa những nhóm đó.

## 4. Ngữ nghĩa "nhóm rỗng" khác "không có nhóm"

Sự khác biệt ở trên ảnh hưởng trực tiếp tới logic báo cáo:

```java
Map<String, List<Ticket>> report = tickets.stream()
        .collect(Collectors.groupingBy(
                Ticket::team,
                Collectors.filtering(
                        ticket -> !ticket.resolved() && ticket.priority() >= 4,
                        Collectors.toList()
                )
        ));

System.out.println(report.containsKey("Mobile")); // true
System.out.println(report.get("Mobile").isEmpty()); // true

System.out.println(report.containsKey("QA"));      // false
System.out.println(report.get("QA"));              // null
```

- `Mobile` **đã xuất hiện trong dữ liệu nguồn**, nhưng không có ticket đạt tiêu chí. Có thể hiển thị "0 ticket cần xử lý".
- `QA` **không xuất hiện trong nguồn**. Không thể kết luận chỉ từ Map này rằng đội QA có tồn tại trong hệ thống hay không.

Vì vậy, không nên đồng nhất `report.get(key) == null` với `report.get(key).isEmpty()`. Nếu code muốn một danh sách an toàn cho việc duyệt khi không có khóa, có thể dùng:

```java
List<Ticket> qaTickets = report.getOrDefault("QA", List.of());
System.out.println(qaTickets.size()); // 0
```

Tuy nhiên, `getOrDefault` chỉ làm cho code đọc dễ hơn; nó **không bổ sung khóa `QA`** vào Map và không xóa bỏ ý nghĩa khác biệt giữa nhóm chưa có trong nguồn với nhóm hiện diện nhưng rỗng.

## 5. Kết hợp filtering với counting và summingInt

Một báo cáo thường chỉ cần số lượng hoặc tổng một thuộc tính, không cần giữ toàn bộ ticket. Lúc đó thay `Collectors.toList()` bằng downstream collector tổng hợp.

### Đếm ticket đạt điều kiện trong mỗi đội

```java
Map<String, Long> urgentCounts = tickets.stream()
        .collect(Collectors.groupingBy(
                Ticket::team,
                Collectors.filtering(
                        ticket -> !ticket.resolved() && ticket.priority() >= 4,
                        Collectors.counting()
                )
        ));

System.out.println(urgentCounts.get("Backend"));  // 1
System.out.println(urgentCounts.get("Frontend")); // 1
System.out.println(urgentCounts.get("Mobile"));   // 0
```

Khi `filtering` không chuyển phần tử nào cho `counting` của một nhóm đã có, collector đếm trả về **`0L`**, không phải `null`. Điều này hữu ích với bảng KPI muốn hiện mọi đội có dữ liệu nguồn.

### Tổng thời gian của các ticket phù hợp

```java
Map<String, Integer> urgentMinutes = tickets.stream()
        .collect(Collectors.groupingBy(
                Ticket::team,
                Collectors.filtering(
                        ticket -> !ticket.resolved() && ticket.priority() >= 4,
                        Collectors.summingInt(Ticket::minutes)
                )
        ));

System.out.println(urgentMinutes.get("Backend"));  // 30
System.out.println(urgentMinutes.get("Frontend")); // 60
System.out.println(urgentMinutes.get("Mobile"));   // 0
```

`summingInt` tích lũy các số nguyên của những phần tử được chuyển vào downstream. Nếu không có phần tử, tổng là **0**. Tổng kiểu `int` có thể bị tràn nếu cộng quá phạm vi biểu diễn; với thời lượng lớn, cân nhắc `summingLong` và kiểu dữ liệu phù hợp.

### Kết quả Optional khi downstream tìm cực trị

Không phải mọi downstream collector đều có "zero" cụ thể:

```java
Map<String, Optional<Ticket>> highestUrgent = tickets.stream()
        .collect(Collectors.groupingBy(
                Ticket::team,
                Collectors.filtering(
                        ticket -> !ticket.resolved() && ticket.priority() >= 4,
                        Collectors.maxBy(
                                Comparator.comparingInt(Ticket::priority)
                        )
                )
        ));

System.out.println(highestUrgent.get("Mobile")); // Optional.empty

highestUrgent.get("Backend")
        .ifPresent(ticket -> System.out.println(ticket.id())); // T01
```

Khóa `Mobile` vẫn hiện diện, nhưng downstream `maxBy` trả về `Optional.empty()` vì không có ticket phù hợp. Tránh gọi `get()` trực tiếp trên Optional rỗng; dùng `ifPresent`, `orElse` hoặc `orElseThrow` tùy ý nghĩa nghiệp vụ.

## 6. filtering và mapping: đúng thứ tự để giữ thông tin cần thiết

`Collectors.mapping` là một downstream collector khác; nó biến đổi từng phần tử trước khi chuyển cho collector bên trong. Kết hợp hai collector này để chỉ lấy **ID** của các ticket đạt điều kiện:

```java
Map<String, List<String>> idsByTeam = tickets.stream()
        .collect(Collectors.groupingBy(
                Ticket::team,
                Collectors.filtering(
                        ticket -> !ticket.resolved() && ticket.priority() >= 4,
                        Collectors.mapping(
                                Ticket::id,
                                Collectors.toList()
                        )
                )
        ));

System.out.println(idsByTeam.get("Backend"));  // [T01]
System.out.println(idsByTeam.get("Frontend")); // [T06]
System.out.println(idsByTeam.get("Mobile"));   // []
```

Đọc từ ngoài vào trong:

1. `groupingBy(Ticket::team, ...)` xác định nhóm của mọi ticket nguồn.
2. `filtering(predicate, ...)` quyết định ticket nào được tích lũy **trong nhóm**.
3. `mapping(Ticket::id, toList())` chỉ lấy mã của ticket được giữ.
4. `toList()` tạo danh sách mã tương ứng.

### Đổi chỗ mapping và filtering sẽ đổi kiểu của predicate

```java
Map<String, List<String>> idsStartingWithT = tickets.stream()
        .collect(Collectors.groupingBy(
                Ticket::team,
                Collectors.mapping(
                        Ticket::id,
                        Collectors.filtering(
                                id -> id.startsWith("T0"),
                                Collectors.toList()
                        )
                )
        ));
```

Ở pipeline này, `filtering` nhận **`String id`** chứ không còn nhận `Ticket`. Nó có thể lọc theo nội dung ID, nhưng không thể gọi `ticket.resolved()` hay `ticket.priority()` vì những thông tin đó đã bị loại bởi `mapping(Ticket::id, ...)`.

**Quy tắc thiết kế:** đặt điều kiện cần thuộc tính của đối tượng gốc **trước** bước chỉ trích xuất một trường; đặt điều kiện cần giá trị đã chuẩn hóa hoặc biến đổi **sau** phép mapping tương ứng. Các thứ tự khác nhau không nhất thiết cho cùng kết quả.

## 7. Lọc trong groupingBy nhiều tầng

`filtering` có thể nằm ở tầng trong cùng của một collector lồng nhiều `groupingBy`. Ví dụ các đơn bán hàng được phân nhóm theo **khu vực → loại hàng**, sau đó chỉ lấy ID của đơn đã thanh toán:

```java
record Sale(
        String id,
        String region,
        String category,
        int quantity,
        boolean paid
) {}

List<Sale> sales = List.of(
        new Sale("S01", "Bắc", "Sách", 2, true),
        new Sale("S02", "Bắc", "Bút", 5, false),
        new Sale("S03", "Nam", "Sách", 3, true),
        new Sale("S04", "Bắc", "Sách", 4, false),
        new Sale("S05", "Nam", "Bút", 1, false)
);

Map<String, Map<String, List<String>>> paidIds = sales.stream()
        .collect(Collectors.groupingBy(
                Sale::region,
                Collectors.groupingBy(
                        Sale::category,
                        Collectors.filtering(
                                Sale::paid,
                                Collectors.mapping(
                                        Sale::id,
                                        Collectors.toList()
                                )
                        )
                )
        ));

System.out.println(paidIds.get("Bắc").get("Sách")); // [S01]
System.out.println(paidIds.get("Bắc").get("Bút"));  // []
System.out.println(paidIds.get("Nam").get("Sách")); // [S03]
System.out.println(paidIds.get("Nam").get("Bút"));  // []
```

Hai lớp classifier `Sale::region` và `Sale::category` đã quan sát các bản ghi ở từng tổ hợp, trước khi `filtering(Sale::paid, ...)` quyết định nội dung danh sách. Vì vậy, tổ hợp **Bắc/Bút** và **Nam/Bút** vẫn xuất hiện với danh sách rỗng.

Nếu đưa `.filter(Sale::paid)` lên trước `collect`, cả hai tổ hợp chỉ có đơn chưa thanh toán sẽ biến mất; nếu một khu vực chỉ có đơn chưa thanh toán, **cả khu vực ấy** cũng biến mất.

Đây là khác biệt quan trọng với báo cáo phân cấp: "loại không bán được trong khu vực đã phát sinh hoạt động" khác với "loại chưa hề xuất hiện trong dữ liệu".

## 8. So sánh với partitioningBy

`Collectors.partitioningBy` phân hoạch theo một predicate Boolean và luôn trả về Map có hai khóa **`true` và `false`**, ngay cả khi một phía không có phần tử.

Ta có thể tiếp tục lồng `filtering` vào downstream của `partitioningBy`:

```java
Map<Boolean, Long> highPriorityCountsByResolution = tickets.stream()
        .collect(Collectors.partitioningBy(
                Ticket::resolved,
                Collectors.filtering(
                        ticket -> ticket.priority() >= 4,
                        Collectors.counting()
                )
        ));

System.out.println(highPriorityCountsByResolution.get(false)); // 2
System.out.println(highPriorityCountsByResolution.get(true));  // 1
```

Trong dữ liệu đang dùng, hai ticket chưa giải quyết có độ ưu tiên cao là `T01` và `T06`; một ticket đã giải quyết có độ ưu tiên cao là `T05`.

Khác biệt giữa hai loại collector:

| Tình huống | `groupingBy(classifier, filtering(...))` | `partitioningBy(predicate, filtering(...))` |
| --- | --- | --- |
| Khóa | Giá trị do classifier trả về | Chỉ `true` và `false` |
| Các khóa không xuất hiện ở nguồn | Không tự sinh | Hai khóa Boolean vẫn hiện diện |
| Bộ lọc trong mỗi nhóm | Có, nhờ downstream `filtering` | Có, nhờ downstream `filtering` |
| Tình huống sử dụng | Phòng ban, khu vực, loại hàng, khóa ghép | Phân loại nhị phân như đã xử lý/chưa xử lý |

Nếu nguồn `tickets` rỗng, `groupingBy` trả về Map không có đội nào, còn `partitioningBy` vẫn chứa hai nhóm Boolean với kết quả downstream rỗng hoặc bằng 0 tùy collector. Đừng nhầm tính chất đặc biệt của `partitioningBy` với `groupingBy`.

## 9. Phối hợp filtering và teeing để lấy nhiều KPI trong một nhóm

Từ Java 12, `Collectors.teeing` cho phép đưa cùng một luồng phần tử đến **hai downstream collector**, rồi kết hợp hai kết quả của chúng. Đặt `filtering` bên ngoài `teeing` khi **hai KPI phải sử dụng cùng một tập phần tử đã lọc**.

```java
record TeamMetrics(long count, int totalMinutes) {}

Map<String, TeamMetrics> metrics = tickets.stream()
        .collect(Collectors.groupingBy(
                Ticket::team,
                Collectors.filtering(
                        ticket -> !ticket.resolved() && ticket.priority() >= 4,
                        Collectors.teeing(
                                Collectors.counting(),
                                Collectors.summingInt(Ticket::minutes),
                                TeamMetrics::new
                        )
                )
        ));

System.out.println(metrics.get("Backend"));
// TeamMetrics[count=1, totalMinutes=30]

System.out.println(metrics.get("Frontend"));
// TeamMetrics[count=1, totalMinutes=60]

System.out.println(metrics.get("Mobile"));
// TeamMetrics[count=0, totalMinutes=0]
```

`teeing` không tự quyết định nhóm hay điều kiện lọc. Nó chỉ thực hiện hai phép thu thập downstream trên các phần tử được chuyển đến:

```text
groupingBy(team)
      |
filtering(urgentAndUnresolved)
      |
      +-------- counting() --------> count
      |
      +-------- summingInt(...) ---> totalMinutes
                                       |
                            TeamMetrics(count, totalMinutes)
```

Nếu hai KPI cần **hai điều kiện khác nhau**, đừng đặt một `filtering` dùng chung ở ngoài rồi dùng chính các KPI đó để suy đoán dữ liệu đã bị loại. Thay vào đó có thể đặt `teeing` bên ngoài, mỗi nhánh có một `filtering` riêng:

```java
record StateMetrics(long unresolved, long highPriority) {}

Map<String, StateMetrics> allStateMetrics = tickets.stream()
        .collect(Collectors.groupingBy(
                Ticket::team,
                Collectors.teeing(
                        Collectors.filtering(
                                ticket -> !ticket.resolved(),
                                Collectors.counting()
                        ),
                        Collectors.filtering(
                                ticket -> ticket.priority() >= 4,
                                Collectors.counting()
                        ),
                        StateMetrics::new
                )
        ));

System.out.println(allStateMetrics.get("Backend"));
// StateMetrics[unresolved=2, highPriority=1]

System.out.println(allStateMetrics.get("Mobile"));
// StateMetrics[unresolved=0, highPriority=1]
```

Hai nhánh trong ví dụ cuối dùng điều kiện **độc lập**; một ticket được phép đóng góp cho cả hai KPI hoặc cho một trong hai. Trong collector nhiều tầng, vị trí `filtering` là một phần của mô hình nghiệp vụ chứ không chỉ là chi tiết cú pháp.

## 10. Giữ dữ liệu kết quả không cho chỉnh sửa

Collector `filtering` có thể dùng downstream khác nhau, kể cả collector tạo danh sách không cho sửa như `toUnmodifiableList` (Java 10+):

```java
Map<String, List<String>> readonlyIds = tickets.stream()
        .collect(Collectors.groupingBy(
                Ticket::team,
                Collectors.filtering(
                        ticket -> !ticket.resolved() && ticket.priority() >= 4,
                        Collectors.mapping(
                                Ticket::id,
                                Collectors.toUnmodifiableList()
                        )
                )
        ));

System.out.println(readonlyIds.get("Mobile")); // []
// readonlyIds.get("Backend").add("T99"); // UnsupportedOperationException
```

Điều quan trọng là **giá trị danh sách** không cho chỉnh sửa, nhưng **Map ngoài** từ `groupingBy` mặc định không được cam kết là unmodifiable. Nếu muốn công bố một Map không cho thay đổi cấu trúc:

```java
Map<String, List<String>> lockedReport = Map.copyOf(readonlyIds);
```

`Map.copyOf` từ chối các khóa hoặc giá trị null, không đảm bảo thứ tự duyệt và chỉ tạo bất biến **nông** cho các đối tượng bên trong. Ở ví dụ này, khóa và phần tử là `String` bất biến, danh sách đã không cho sửa nên kết quả tương đối dễ chia sẻ an toàn.

Một lựa chọn khác là dùng `Collectors.collectingAndThen` làm downstream, ví dụ:

```java
Map<String, List<String>> readonlyViaFinisher = tickets.stream()
        .collect(Collectors.groupingBy(
                Ticket::team,
                Collectors.filtering(
                        ticket -> !ticket.resolved(),
                        Collectors.mapping(
                                Ticket::id,
                                Collectors.collectingAndThen(
                                        Collectors.toList(),
                                        List::copyOf
                                )
                        )
                )
        ));
```

`List.copyOf` có từ Java 10 và từ chối phần tử `null`. Dùng phương án nào phụ thuộc nhu cầu phiên bản Java, cách tạo kết quả và chính sách với null. Không được giả định `Collectors.toList()` cam kết luôn trả về danh sách có thể sửa.

## 11. Các lỗi với null và classifier

`Collectors.groupingBy` không chấp nhận classifier trả về **khóa null**. Một `filtering` đặt bên trong không thể che giấu lỗi đó vì classifier được dùng **trước** downstream.

```java
record Entry(String team, boolean valid) {}

List<Entry> entries = List.of(
        new Entry("Backend", true),
        new Entry(null, false)
);

// SAI: phần tử có team null vẫn được classifier xử lý trước downstream.
Map<String, Long> invalid = entries.stream()
        .collect(Collectors.groupingBy(
                Entry::team,
                Collectors.filtering(
                        Entry::valid,
                        Collectors.counting()
                )
        ));
// Ném NullPointerException dù entry team=null có valid=false.
```

Trong ví dụ trên, nếu quy tắc nghiệp vụ là **loại toàn bộ bản ghi không có team**, cần lọc chúng ở **Stream ngoài**:

```java
Map<String, Long> validCounts = entries.stream()
        .filter(entry -> entry.team() != null)
        .collect(Collectors.groupingBy(
                Entry::team,
                Collectors.filtering(
                        Entry::valid,
                        Collectors.counting()
                )
        ));

System.out.println(validCounts.get("Backend")); // 1
```

Hãy phân biệt hai tầng xử lý:

- **Stream.filter** trước `groupingBy` là lựa chọn hợp lý cho những bản ghi **không thể hoặc không nên phân loại**, ví dụ thiếu khóa nhóm, dữ liệu bị hủy hoặc không thuộc phạm vi báo cáo.
- **Collectors.filtering** ở downstream xử lý **điều kiện lựa chọn trong nhóm đã được xác định**, nhằm giữ trạng thái của nhóm đó trong báo cáo.

Khi đầu vào có phần tử `null` (không chỉ trường `team` null), `Entry::team` cũng sẽ gây lỗi. Cần dùng `filter(Objects::nonNull)` trước classifier hoặc định nghĩa chính sách dữ liệu thiếu.

Nếu `filtering` chuyển một đối tượng null tới downstream như `Collectors.mapping(Entry::team, ...)`, vẫn có thể gây lỗi trong mapping; không nên coi `filtering` là cơ chế kiểm tra null tự động.

## 12. Thứ tự phần tử, thứ tự khóa và xử lý song song

### Thứ tự khóa của Map

`groupingBy` mặc định không cam kết kiểu Map hay thứ tự lặp khóa. Để hiển thị nhóm theo **thứ tự gặp đầu tiên** từ một Stream tuần tự có thứ tự, có thể chỉ rõ `LinkedHashMap::new`:

```java
Map<String, List<String>> orderedGroups = tickets.stream()
        .collect(Collectors.groupingBy(
                Ticket::team,
                LinkedHashMap::new,
                Collectors.filtering(
                        ticket -> !ticket.resolved() && ticket.priority() >= 4,
                        Collectors.mapping(Ticket::id, Collectors.toList())
                )
        ));

System.out.println(orderedGroups.keySet());
// [Backend, Frontend, Mobile]
```

Ở ví dụ tuần tự, các đội xuất hiện lần đầu theo thứ tự Backend → Frontend → Mobile. Việc nhóm `Mobile` có danh sách rỗng không khiến khóa ấy bị xóa.

### Thứ tự phần tử trong nhóm

Với `List.stream()` có encounter order, `groupingBy` cùng `toList` ở downstream có thể giữ thứ tự xuất hiện của các ticket được chuyển vào từng nhóm. Trong pipeline song song, thứ tự **thực thi predicate và mapper** không được bảo đảm; không dùng tác dụng phụ trong lambda để suy ra hay áp đặt thứ tự.

Nếu nhóm cần danh sách được **sắp theo độ ưu tiên**, hãy định nghĩa bước sắp hoặc comparator rõ ràng; `filtering` không tự sắp xếp phần tử.

### Parallel Stream và groupingByConcurrent

`groupingBy` không phải concurrent collector. Khi dùng `parallelStream()`, framework có thể tạo nhiều Map từng phần rồi kết hợp. Các collector lồng như `filtering`, `mapping`, `counting` phải tuân thủ hợp đồng kết hợp của chúng.

```java
Map<String, Long> parallelCounts = tickets.parallelStream()
        .collect(Collectors.groupingBy(
                Ticket::team,
                Collectors.filtering(
                        ticket -> !ticket.resolved() && ticket.priority() >= 4,
                        Collectors.counting()
                )
        ));

System.out.println(parallelCounts.get("Mobile")); // 0
```

Nếu không cần thứ tự, có thể cân nhắc `groupingByConcurrent`:

```java
ConcurrentMap<String, Long> concurrentCounts = tickets.parallelStream()
        .collect(Collectors.groupingByConcurrent(
                Ticket::team,
                Collectors.filtering(
                        ticket -> !ticket.resolved() && ticket.priority() >= 4,
                        Collectors.counting()
                )
        ));
```

`groupingByConcurrent` là collector concurrent, unordered, cho phép chiến lược thu thập khác. Tuy nhiên, nó **không tự khiến predicate có trạng thái hoặc thao tác sửa nguồn trở nên an toàn**; cũng không cam kết nhanh hơn trong mọi tình huống.

## 13. Tính lazy, non-interference và chi phí xử lý

`Stream.filter` là thao tác trung gian lazy; `Collectors.filtering` là một phần của **collector dùng ở terminal operation**. Cả hai điều kiện chỉ được đánh giá khi terminal operation bắt đầu xử lý phần tử phù hợp với pipeline.

```java
Stream<Ticket> pipeline = tickets.stream()
        .filter(ticket -> ticket.priority() > 0);

// Chỉ lúc collect() diễn ra, pipeline mới được tiêu thụ.
Map<String, Long> result = pipeline.collect(
        Collectors.groupingBy(
                Ticket::team,
                Collectors.filtering(
                        ticket -> !ticket.resolved(),
                        Collectors.counting()
                )
        )
);
```

Với `groupingBy(classifier, filtering(...))`, classifier được áp dụng để xác định nhóm cho mọi phần tử đã qua các thao tác Stream ở phía trước; downstream `filtering` không tiết kiệm chi phí phân loại những phần tử bị loại.

Vì vậy:

- Nếu chỉ quan tâm các bản ghi đạt điều kiện và **không cần nhóm rỗng**, `Stream.filter` trước `groupingBy` thường gọn và có thể giảm số lượng phần tử phải phân loại.
- Nếu **giữ nhóm có dữ liệu nguồn nhưng không có phần tử đạt điều kiện** là một phần của hợp đồng báo cáo, `Collectors.filtering` là cách biểu đạt đúng, kể cả khi có thêm chi phí phân loại.
- Nếu chỉ cần số đếm hoặc tổng, dùng `counting`/`summingInt` ở downstream thay vì lưu tất cả phần tử vào List lớn.

Predicate nên **không can thiệp nguồn** và **không dựa vào trạng thái mutable của bên ngoài**:

```java
List<Ticket> mutableTickets = new ArrayList<>(tickets);

// SAI: thay đổi chính nguồn trong lúc collect đang duyệt nó.
Map<String, Long> broken = mutableTickets.stream()
        .collect(Collectors.groupingBy(
                Ticket::team,
                Collectors.filtering(
                        ticket -> {
                            mutableTickets.clear();
                            return ticket.priority() >= 4;
                        },
                        Collectors.counting()
                )
        ));
```

Việc sửa nguồn ở đây vi phạm non-interference, có thể gây `ConcurrentModificationException` hoặc hành vi không đáng tin cậy. Cũng tránh dùng biến đếm ngoài để quyết định predicate, nhất là trong parallel pipeline. Nếu cần cập nhật nguồn, hãy hoàn tất phép thu thập trước, sau đó cập nhật trong bước riêng.

Với dữ liệu rất lớn và yêu cầu KPI theo nhiều nhóm, hãy xem xét bộ nhớ của Map kết quả, số lượng nhóm, chi phí classifier và downstream, chi phí phối hợp khi chạy song song. Kết quả đúng về mặt nghiệp vụ phải được ưu tiên trước tối ưu tốc độ.

## 14. Ví dụ Java 17+ hoàn chỉnh: bảng KPI theo đội

Ví dụ sau tạo ba báo cáo độc lập: danh sách ID ticket khẩn chưa giải quyết, số lượng ticket khẩn và bộ chỉ số số lượng/thời gian. Đội `Mobile` phải **xuất hiện với dữ liệu rỗng hoặc bằng 0** dù không có ticket thỏa tiêu chí.

```java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public class FilteringWithinGroupsDemo {
    record Ticket(
            String id,
            String team,
            int priority,
            boolean resolved,
            int minutes
    ) {}

    record Metrics(long count, int totalMinutes) {}

    static boolean urgentUnresolved(Ticket ticket) {
        return !ticket.resolved() && ticket.priority() >= 4;
    }

    public static void main(String[] args) {
        List<Ticket> tickets = List.of(
                new Ticket("T01", "Backend", 5, false, 30),
                new Ticket("T02", "Frontend", 2, false, 15),
                new Ticket("T03", "Backend", 3, true, 20),
                new Ticket("T04", "Backend", 1, false, 45),
                new Ticket("T05", "Mobile", 4, true, 10),
                new Ticket("T06", "Frontend", 4, false, 60)
        );

        Map<String, List<String>> urgentIds = tickets.stream()
                .collect(Collectors.groupingBy(
                        Ticket::team,
                        LinkedHashMap::new,
                        Collectors.filtering(
                                FilteringWithinGroupsDemo::urgentUnresolved,
                                Collectors.mapping(
                                        Ticket::id,
                                        Collectors.toList()
                                )
                        )
                ));

        Map<String, Long> urgentCounts = tickets.stream()
                .collect(Collectors.groupingBy(
                        Ticket::team,
                        LinkedHashMap::new,
                        Collectors.filtering(
                                FilteringWithinGroupsDemo::urgentUnresolved,
                                Collectors.counting()
                        )
                ));

        Map<String, Metrics> kpis = tickets.stream()
                .collect(Collectors.groupingBy(
                        Ticket::team,
                        LinkedHashMap::new,
                        Collectors.filtering(
                                FilteringWithinGroupsDemo::urgentUnresolved,
                                Collectors.teeing(
                                        Collectors.counting(),
                                        Collectors.summingInt(Ticket::minutes),
                                        Metrics::new
                                )
                        )
                ));

        System.out.println(urgentIds);
        // {Backend=[T01], Frontend=[T06], Mobile=[]}

        System.out.println(urgentCounts);
        // {Backend=1, Frontend=1, Mobile=0}

        System.out.println(kpis);
        // {Backend=Metrics[count=1, totalMinutes=30],
        //  Frontend=Metrics[count=1, totalMinutes=60],
        //  Mobile=Metrics[count=0, totalMinutes=0]}

        System.out.println(urgentIds.containsKey("Mobile")); // true
        System.out.println(urgentIds.containsKey("QA"));     // false
    }
}
```

**Phân tích:**

1. `Ticket::team` phân nhóm toàn bộ ticket. `LinkedHashMap::new` dùng để giữ thứ tự các nhóm xuất hiện trong nguồn List ở pipeline tuần tự.
2. `urgentUnresolved` là predicate **thuần về dữ liệu đầu vào**: nó chỉ đọc `Ticket`, không sửa nguồn hoặc biến dùng chung.
3. `filtering` giữ các nhóm đã xuất hiện kể cả khi không có ticket nào được đưa vào downstream.
4. `mapping(Ticket::id, toList())` chỉ đưa ID ticket đạt điều kiện vào danh sách.
5. `counting` cho kết quả `0` ở nhóm `Mobile`; `teeing` kết hợp số đếm và tổng thời gian.
6. Mỗi báo cáo tạo một Stream mới từ `tickets`. Không cố tái sử dụng một Stream đã bị `collect` tiêu thụ.

Trong ứng dụng thực tế, nếu cả ba báo cáo luôn cần được tính trên cùng một tập dữ liệu lớn, có thể thiết kế một downstream collector tổng hợp phù hợp để tránh duyệt nguồn nhiều lần. Ví dụ ở đây ưu tiên học rõ hợp đồng của từng cách phối hợp collector.

## 15. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Nhóm không có ticket phù hợp biến mất | Đặt `Stream.filter` trước `groupingBy` | Dùng downstream `Collectors.filtering` nếu muốn giữ nhóm đã xuất hiện. |
| Nhóm chưa hề xuất hiện vẫn không có trong Map | `groupingBy` chỉ tạo khóa từ phần tử được classifier gặp | Kết hợp danh mục nhóm riêng nếu cần đủ mọi khóa hợp lệ. |
| Không gọi được `filtering` như thao tác Stream | `Collectors.filtering` trả về `Collector`, không phải `Stream` | Truyền nó vào `collect` hoặc downstream của `groupingBy`. |
| Predicate không truy cập được trường của đối tượng gốc | Đặt `mapping` trước `filtering` đã biến phần tử thành kiểu khác | Đổi thứ tự lồng collector hoặc lưu đủ thông tin cần lọc. |
| `NullPointerException` ở classifier dù downstream bỏ bản ghi | Phân nhóm diễn ra trước downstream filtering | Loại/xử lý bản ghi không thể phân loại bằng `Stream.filter` phía trước. |
| Gọi `get(...).isEmpty()` và lỗi với nhóm không có | Map không có key đó nên `get` trả null | Dùng `containsKey`, `getOrDefault` và phân biệt hai trạng thái. |
| Trông đợi kết quả List rỗng nhưng nhận `Optional.empty` | Dùng `maxBy`/`minBy` thay vì `toList` | Xử lý theo kiểu kết quả downstream thực tế. |
| Giả định thứ tự khóa của `groupingBy` | Map mặc định không cam kết thứ tự | Chọn `LinkedHashMap` khi cần thứ tự xuất hiện tuần tự. |
| KPI theo nhóm sai vì mọi nhánh dùng cùng một điều kiện | Đặt `filtering` chung ngoài `teeing` trong khi các KPI cần tiêu chí khác nhau | Dùng `teeing` với mỗi nhánh có `filtering` riêng. |
| Thống kê sai hoặc bất ổn khi chạy song song | Predicate phụ thuộc biến dùng chung hoặc sửa nguồn | Giữ predicate stateless, non-interfering; kiểm thử với dữ liệu và số nhóm thực tế. |

## 16. Bài tập thực hành

Cho dữ liệu nhân viên:

```java
record Employee(String department, String name, int age, boolean active) {}

List<Employee> employees = List.of(
        new Employee("IT", "An", 28, true),
        new Employee("IT", "Bình", 21, false),
        new Employee("HR", "Chi", 35, false),
        new Employee("Sales", "Dũng", 26, true),
        new Employee("HR", "Hà", 29, false)
);
```

**Yêu cầu:**

1. Nhóm nhân viên theo `department`, dùng `Collectors.filtering` để chỉ giữ nhân viên `active` trong từng nhóm.
2. Chuyển kết quả sang `Map<String, List<String>>` chỉ chứa tên nhân viên active.
3. Đếm số nhân viên active theo phòng ban. Kết quả phòng `HR` phải có số đếm `0`.
4. So sánh với việc dùng `employees.stream().filter(Employee::active)` trước `groupingBy`.
5. Viết báo cáo gồm hai KPI theo phòng ban: số nhân viên active và số nhân viên có tuổi từ 30 trở lên (hai điều kiện **độc lập**).

**Lời giải tham khảo:**

```java
Map<String, List<String>> activeNames = employees.stream()
        .collect(Collectors.groupingBy(
                Employee::department,
                Collectors.filtering(
                        Employee::active,
                        Collectors.mapping(
                                Employee::name,
                                Collectors.toList()
                        )
                )
        ));

System.out.println(activeNames.get("IT"));    // [An]
System.out.println(activeNames.get("HR"));    // []
System.out.println(activeNames.get("Sales")); // [Dũng]

Map<String, Long> activeCounts = employees.stream()
        .collect(Collectors.groupingBy(
                Employee::department,
                Collectors.filtering(
                        Employee::active,
                        Collectors.counting()
                )
        ));

System.out.println(activeCounts.get("HR")); // 0

Map<String, List<Employee>> filteredFirst = employees.stream()
        .filter(Employee::active)
        .collect(Collectors.groupingBy(Employee::department));

System.out.println(filteredFirst.containsKey("HR")); // false

record EmployeeMetrics(long active, long agedAtLeast30) {}

Map<String, EmployeeMetrics> twoKpis = employees.stream()
        .collect(Collectors.groupingBy(
                Employee::department,
                Collectors.teeing(
                        Collectors.filtering(
                                Employee::active,
                                Collectors.counting()
                        ),
                        Collectors.filtering(
                                employee -> employee.age() >= 30,
                                Collectors.counting()
                        ),
                        EmployeeMetrics::new
                )
        ));

System.out.println(twoKpis.get("HR"));
// EmployeeMetrics[active=0, agedAtLeast30=1]
```

Ở yêu cầu cuối, `HR` có **0 nhân viên active** nhưng có **1 nhân viên từ 30 tuổi trở lên** (Chi, 35 tuổi); hai phép lọc cần tồn tại ở hai nhánh riêng. Bài tập này giúp phân biệt việc giữ nhóm, đổi kiểu phần tử bằng `mapping` và lựa chọn vị trí `filtering` trong phép tổng hợp nhiều tầng.

**Tự mở rộng:** Thêm một phòng ban `Legal` không có nhân viên nào trong danh sách. `groupingBy` có tự tạo khóa `Legal` không? Nếu hệ thống có danh mục phòng ban riêng, hãy đề xuất bước bổ sung khóa với giá trị rỗng sau thu thập và giải thích vì sao không nên tạo dữ liệu giả ngay trong predicate.

## Ghi nhớ

`Collectors.filtering(predicate, downstream)` là **downstream collector** để lọc những phần tử **sau khi classifier của nhóm đã được áp dụng**. Đặt nó trong `groupingBy` giúp giữ lại những khóa nhóm có dữ liệu nguồn, ngay cả khi tất cả phần tử của nhóm bị lọc bỏ. Điều này khác `Stream.filter` chạy trước `groupingBy`, vốn khiến nhóm không còn phần tử phù hợp biến mất hoàn toàn.

Loại giá trị của nhóm phụ thuộc downstream: `toList` cho danh sách rỗng, `counting` cho `0`, `summingInt` cho `0` và `maxBy` cho `Optional.empty()` khi không có phần tử phù hợp. Khi ghép với `mapping` hoặc `teeing`, hãy chú ý kiểu phần tử và ý nghĩa của từng điều kiện. Luôn giữ predicate stateless, không can thiệp nguồn; xử lý khóa null trước classifier; không mặc định thứ tự Map hay lợi ích của `parallelStream`; và chỉ bổ sung những nhóm chưa từng xuất hiện bằng nguồn danh mục đáng tin cậy.
