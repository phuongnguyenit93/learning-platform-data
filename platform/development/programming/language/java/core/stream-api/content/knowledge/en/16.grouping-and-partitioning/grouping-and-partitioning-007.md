# Xử lý khóa phân nhóm null và nhóm không có phần tử

Trong Java Stream API, `Collectors.groupingBy` có thể biến nhiều bản ghi thành một `Map<K, List<T>>`, còn `Collectors.partitioningBy` chia chúng thành hai nhánh `true` và `false`. Tuy nhiên, dữ liệu thực tế thường có **khóa phân nhóm thiếu thông tin** hoặc một **nhóm dự kiến không nhận được phần tử nào**. Nếu không xác định rõ cách xử lý, báo cáo có thể ném ngoại lệ, bỏ sót nhóm, hiển thị sai số lượng hoặc nhầm giữa “không có dữ liệu” với “có nhóm nhưng chưa có dữ liệu phù hợp”.

Bài học thuộc chương **Phân nhóm và phân hoạch** của module `JAVA_STREAM_API`. Nội dung tập trung vào hợp đồng của `groupingBy` khi classifier trả `null`, cách biểu diễn giá trị phân nhóm vắng mặt, phân biệt nhóm **không xuất hiện** với nhóm **rỗng do lọc downstream**, sự khác biệt của `partitioningBy`, và tác động của thứ tự thao tác, nguồn parallel, tài nguyên và hiệu năng. Những khái niệm này kết nối trực tiếp với pipeline lazy, `filter`, `map` và `collect`.

Các ví dụ cơ bản dùng cú pháp Java 8. Phần sử dụng `Collectors.filtering` được ghi rõ là yêu cầu **Java 9 trở lên**.

## 1. Phân biệt ba trạng thái rất dễ nhầm

Giả sử quản lý công việc theo nhóm `"Backend"`, `"Frontend"` và `"QA"`.

Có ít nhất ba tình huống:

1. **Khóa của một công việc là `null`**: công việc chưa được phân nhóm. Đây là vấn đề về giá trị do *classifier* trả về.
2. **Không có công việc nào thuộc `"QA"`**: nếu chỉ thu thập từ danh sách công việc, `groupingBy` thường **không tạo khóa `"QA"`**.
3. **Có công việc thuộc `"Frontend"`, nhưng không công việc nào đạt một điều kiện lọc ở downstream collector**: khóa `"Frontend"` có thể vẫn xuất hiện với **danh sách rỗng** hoặc kết quả `count = 0`.

Ba trạng thái không tương đương:

```text
Dữ liệu đầu vào
   |
   +-- Task(team = null) ----------> classifier không có khóa
   |
   +-- Không tồn tại Task(team=QA) --> Map không có khóa QA
   |
   +-- Task(team=Frontend)
            |
            +-- downstream filter loại hết --> Frontend = []
```

Chúng cần các chiến lược xử lý khác nhau. `Optional.empty()`, không có key trong Map và `Collections.emptyList()` không phải một khái niệm duy nhất.

## 2. groupingBy hoạt động thế nào?

Một biểu thức thường gặp:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

List<String> words = Arrays.asList("ant", "apple", "bear", "bird");

Map<Character, List<String>> byFirstLetter = words.stream()
        .collect(Collectors.groupingBy(text -> text.charAt(0)));

System.out.println(byFirstLetter.get('a')); // [ant, apple]
System.out.println(byFirstLetter.get('b')); // [bear, bird]
System.out.println(byFirstLetter.containsKey('c')); // false
```

`groupingBy(classifier)` áp dụng hàm `classifier` lên từng phần tử đã đi qua các thao tác trung gian trước đó, rồi chuyển phần tử ấy đến bộ tích lũy của nhóm tương ứng. Mặc định, downstream collector là `toList()`.

Có thể tưởng tượng hợp đồng logic:

```text
Stream<T>
   │
   ├── classifier(t) -> k1 -> tích lũy nhóm k1
   ├── classifier(t) -> k2 -> tích lũy nhóm k2
   └── classifier(t) -> k1 -> tích lũy nhóm k1
                              │
                              ▼
                         Map<K,List<T>>
```

Map chứa các khóa **thực sự xuất hiện ở những phần tử được phân loại**. `groupingBy` không biết danh sách tất cả giá trị khóa hợp lệ trong miền nghiệp vụ và không tự tạo nhóm cho những khóa chưa từng thấy.

## 3. Khóa null: groupingBy không chấp nhận classifier trả null

Đây là lỗi phổ biến nhất:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

final class Task {
    private final String id;
    private final String team;
    private final boolean done;

    Task(String id, String team, boolean done) {
        this.id = id;
        this.team = team;
        this.done = done;
    }

    String id()   { return id; }
    String team() { return team; }
    boolean done() { return done; }
}

List<Task> tasks = Arrays.asList(
        new Task("T01", "Backend", true),
        new Task("T02", null, false),
        new Task("T03", "Frontend", false),
        new Task("T04", "Backend", false)
);
```

Nếu chạy:

```java
// Ví dụ lỗi: cố ý minh họa classifier trả null.
Map<String, List<Task>> invalid = tasks.stream()
        .collect(Collectors.groupingBy(Task::team));
```

Pipeline sẽ ném `NullPointerException` khi `Task::team` trả `null`. Thông điệp ngoại lệ trên nhiều JDK là `element cannot be mapped to a null key`.

**Quan trọng:** kể cả một số triển khai `Map` (ví dụ `HashMap`) có hỗ trợ **khóa `null`**, `Collectors.groupingBy` vẫn không chấp nhận **kết quả phân loại `null`**. Truyền `HashMap::new` vào overload có `mapFactory` cũng **không bỏ được quy tắc này**.

Tương tự, `Collectors.groupingByConcurrent` không nên được dùng để xử lý khóa phân nhóm `null`; nó cũng yêu cầu khóa classifier hợp lệ, và các cấu trúc `ConcurrentMap` thông dụng không nhận khóa `null`.

### Phân biệt phần tử nguồn null và khóa null

`List<Task>` còn có thể chứa **chính phần tử `null`**, khiến method reference `Task::team` ném `NullPointerException` trước khi trả được bất kỳ khóa nào. Đó là vấn đề đầu vào khác với một đối tượng Task hợp lệ có trường `team == null`.

Nếu danh sách có thể chứa Task null:

```java
import java.util.Objects;

Map<String, List<Task>> safeInput = tasks.stream()
        .filter(Objects::nonNull)
        .filter(task -> task.team() != null)
        .collect(Collectors.groupingBy(Task::team));
```

Ở đây hai bước lọc xử lý hai nguyên nhân khác nhau: bản ghi null và khóa null. Chỉ dùng `filter(Objects::nonNull)` **không đủ** để loại Task có team null.

## 4. Chính sách A: loại bản ghi chưa có khóa

Nếu yêu cầu báo cáo chỉ tính các công việc đã được phân công, có thể bỏ những bản ghi có `team == null` ngay trước `groupingBy`:

```java
Map<String, List<Task>> assignedOnly = tasks.stream()
        .filter(task -> task.team() != null)
        .collect(Collectors.groupingBy(Task::team));

System.out.println(assignedOnly.get("Backend").size());  // 2
System.out.println(assignedOnly.get("Frontend").size()); // 1
System.out.println(assignedOnly.containsKey("QA"));      // false
```

Ưu điểm: đơn giản, rõ ý nghĩa, tránh phải biểu diễn nhóm thiếu khóa. Nhược điểm: **công việc T02 không còn xuất hiện trong báo cáo này**.

Chỉ áp dụng chính sách lọc khi việc bỏ dữ liệu là chủ đích nghiệp vụ. Nếu hệ thống cần kiểm toán, thống kê số lượng chưa được phân công hoặc hiển thị cảnh báo thiếu thông tin, không nên âm thầm loại Task ấy.

## 5. Chính sách B: dùng một khóa đại diện rõ ràng

Nếu muốn giữ cả các công việc chưa phân công, ta có thể chuyển `null` thành một khóa **không null**:

```java
private static final String UNASSIGNED = "[CHUA_PHAN_NHOM]";

// Minh họa trong phạm vi lớp chứa hằng UNASSIGNED:
Map<String, List<Task>> byTeam = tasks.stream()
        .collect(Collectors.groupingBy(
                task -> task.team() == null
                        ? UNASSIGNED
                        : task.team()
        ));

System.out.println(byTeam.get(UNASSIGNED).size()); // 1
System.out.println(byTeam.get("Backend").size());   // 2
```

Cách này tiện khi xuất báo cáo hoặc hiển thị giao diện. Tuy nhiên, **khóa thay thế không được va chạm với một giá trị khóa thật**. Nếu người dùng thực sự có thể tạo team tên `"[CHUA_PHAN_NHOM]"`, hai nhóm sẽ bị nhập làm một.

Các lựa chọn tốt hơn cho dự án thật gồm:

- Dành riêng mã định danh nội bộ không được dùng làm team ID, và chỉ chuyển mã này thành nhãn giao diện ở bước hiển thị.
- Sử dụng enum hoặc kiểu khóa miền nghiệp vụ có trường hợp `UNASSIGNED` riêng biệt.
- Dùng `Optional<String>` làm khóa để không phải phát minh một chuỗi giả.

Không nên chọn `""` một cách tùy tiện nếu chuỗi rỗng cũng là giá trị dữ liệu cần phân biệt.

## 6. Chính sách C: dùng Optional làm khóa Map

`Optional.ofNullable` chuyển team `null` thành `Optional.empty()`. Quan trọng: **`Optional.empty()` là một đối tượng Optional không null**, nên có thể dùng làm khóa trong `groupingBy`.

```java
import java.util.Optional;

Map<Optional<String>, List<Task>> optionalGroups = tasks.stream()
        .collect(Collectors.groupingBy(
                task -> Optional.ofNullable(task.team())
        ));

System.out.println(
        optionalGroups.get(Optional.empty()).size()
); // 1

System.out.println(
        optionalGroups.get(Optional.of("Backend")).size()
); // 2
```

Mô hình này biểu diễn rõ hai trường hợp:

- `Optional.of("Backend")`: khóa team có giá trị.
- `Optional.empty()`: team chưa tồn tại.

Vì `Optional` có `equals`/`hashCode` phù hợp, nhiều Optional chứa cùng team được xem là cùng khóa. Đối với một Map kết quả dùng trong nội bộ xử lý, cách này giữ được sự khác biệt giữa thiếu khóa và tên team thật.

Đổi lại, API đầu ra sẽ là `Map<Optional<String>, List<Task>>`, nên những nơi đọc Map phải chủ động xử lý Optional. Không nhất thiết xuất trực tiếp kiểu khóa này ra JSON, SQL hoặc giao diện; ở ranh giới hệ thống, nên chuyển thành mô hình báo cáo rõ nghĩa.

### Nếu null phải là lỗi dữ liệu

Có những trường hợp team là bắt buộc, và thiếu team là **lỗi** chứ không phải một nhóm. Khi đó kiểm tra trước khi collect sẽ rõ hơn:

```java
import java.util.Objects;

Map<String, List<Task>> strictGroups = tasks.stream()
        .collect(Collectors.groupingBy(task ->
                Objects.requireNonNull(
                        task.team(),
                        "Task " + task.id() + " chua co team"
                )
        ));
```

Trên dữ liệu ví dụ, đoạn này cố ý ném `NullPointerException` kèm thông điệp nghiệp vụ. Nếu hệ thống muốn báo nhiều bản ghi lỗi trong một lần nhập, cần bước kiểm tra/thu thập lỗi riêng thay vì dừng ở lỗi đầu tiên.

## 7. Nhóm không có phần tử: groupingBy không tự sinh khóa

Nguồn chỉ chứa team Backend và Frontend:

```java
Map<String, Long> counts = tasks.stream()
        .filter(task -> task.team() != null)
        .collect(Collectors.groupingBy(
                Task::team,
                Collectors.counting()
        ));

System.out.println(counts.get("Backend"));      // 2
System.out.println(counts.get("Frontend"));     // 1
System.out.println(counts.containsKey("QA"));   // false
System.out.println(counts.get("QA"));           // null
```

Kết quả `null` của `counts.get("QA")` ở đây có nghĩa **Map không chứa khóa QA**, không phải classifier đã được phép trả null. Hai sự kiện hoàn toàn khác nhau.

Đừng nhầm:

```java
counts.getOrDefault("QA", 0L) // trả 0L, nhưng KHÔNG thêm khóa QA
```

`getOrDefault` chỉ trả về giá trị dự phòng cho lần tra cứu. Sau lời gọi này, `counts.containsKey("QA")` vẫn bằng `false`.

Tương tự:

```java
Map<String, List<Task>> groups = tasks.stream()
        .filter(task -> task.team() != null)
        .collect(Collectors.groupingBy(Task::team));

List<Task> qa = groups.getOrDefault(
        "QA",
        java.util.Collections.emptyList()
);

System.out.println(qa.isEmpty());             // true
System.out.println(groups.containsKey("QA")); // false
```

`qa` ở đây là danh sách dự phòng, không phải một nhóm mới trong Map.

## 8. Muốn luôn hiện tất cả nhóm dự kiến? Bổ sung tập khóa miền nghiệp vụ

Nếu báo cáo bắt buộc có Backend, Frontend và QA kể cả khi chưa có công việc, ta phải cung cấp **danh sách các team dự kiến** từ chính yêu cầu nghiệp vụ. Stream của Task không tự biết danh sách này.

### Cách 1: chuẩn hóa Map sau khi collect

```java
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

List<String> expectedTeams = Arrays.asList(
        "Backend", "Frontend", "QA"
);

Map<String, List<Task>> grouped = tasks.stream()
        .filter(task -> task.team() != null)
        .collect(Collectors.groupingBy(Task::team));

Map<String, List<Task>> report = new LinkedHashMap<>();

for (String team : expectedTeams) {
    report.put(
            team,
            grouped.getOrDefault(
                    team,
                    java.util.Collections.emptyList()
            )
    );
}

System.out.println(report.get("QA").size()); // 0
System.out.println(report.containsKey("QA")); // true
```

Cách này có hai ưu điểm:

1. Các team xuất hiện theo thứ tự định nghĩa trong `expectedTeams` nhờ `LinkedHashMap`.
2. Nhóm không có phần tử vẫn được biểu diễn tường minh bằng một danh sách rỗng.

**Lưu ý:** `Collections.emptyList()` là danh sách không sửa được. Nếu báo cáo cần bổ sung phần tử sau khi thu thập, hãy tạo `new ArrayList<>()` cho nhóm rỗng thay vì gọi `add` trên danh sách bất biến. Không nên sửa nội dung các danh sách khi kết quả đang được đọc ở nhiều luồng mà không có cơ chế đồng bộ.

Nếu muốn giữ cả các team nằm ngoài tập dự kiến, hãy quy định rõ chính sách bổ sung chúng vào báo cáo. Vòng lặp trên chỉ tạo báo cáo cho các team trong `expectedTeams`.

### Cách 2: chỉ bổ sung nhóm thiếu

```java
Map<String, List<Task>> mutableGroups = tasks.stream()
        .filter(task -> task.team() != null)
        .collect(Collectors.groupingBy(Task::team));

for (String team : expectedTeams) {
    mutableGroups.computeIfAbsent(
            team,
            key -> new java.util.ArrayList<Task>()
    );
}

System.out.println(mutableGroups.containsKey("QA")); // true
System.out.println(mutableGroups.get("QA").isEmpty()); // true
```

Cách này bổ sung các nhóm thiếu ngay trên Map đã thu thập, đồng thời giữ các nhóm đã có. Nhưng Map do `groupingBy` trả về theo overload mặc định **không cam kết kiểu cụ thể, mutability hay thứ tự duyệt**. Nếu dự án cần sửa Map sau đó như một phần hợp đồng đáng tin cậy, nên chỉ định `mapFactory` để tạo một Map mutable đã biết:

```java
Map<String, List<Task>> mutableGroups = tasks.stream()
        .filter(task -> task.team() != null)
        .collect(Collectors.groupingBy(
                Task::team,
                LinkedHashMap::new,
                Collectors.toList()
        ));

for (String team : expectedTeams) {
    mutableGroups.computeIfAbsent(
            team,
            key -> new java.util.ArrayList<Task>()
    );
}
```

Nếu muốn **đúng thứ tự của expectedTeams** ngay cả khi các nhóm gốc gặp theo thứ tự khác, cách tạo một `LinkedHashMap` mới từ danh sách khóa dự kiến ở **Cách 1** rõ nghĩa hơn.

## 9. Filter trước grouping khác với filtering bên trong grouping

Đây là điểm tinh tế nhất của nhóm rỗng.

Giả sử muốn nhóm công việc theo team nhưng chỉ giữ **các công việc đã hoàn thành**. Dữ liệu có team Frontend nhưng tất cả công việc của Frontend chưa hoàn thành.

### Lọc ở upstream: nhóm có thể biến mất

```java
Map<String, List<Task>> doneOnly = tasks.stream()
        .filter(task -> task.team() != null)
        .filter(Task::done)
        .collect(Collectors.groupingBy(Task::team));

System.out.println(doneOnly.containsKey("Backend"));  // true
System.out.println(doneOnly.containsKey("Frontend")); // false
```

Vì chỉ những Task `done == true` mới đi đến `groupingBy`, classifier **chưa bao giờ thấy** khóa Frontend. Không có cách nào để Collector tự suy ra Frontend là một nhóm cần hiển thị.

### Lọc ở downstream: nhóm được giữ dù kết quả rỗng

Từ **Java 9**, `Collectors.filtering(predicate, downstream)` cho phép kiểm tra từng phần tử **sau khi đã xác định nhóm**:

```java
Map<String, List<Task>> doneByTeam = tasks.stream()
        .filter(task -> task.team() != null)
        .collect(Collectors.groupingBy(
                Task::team,
                Collectors.filtering(
                        Task::done,
                        Collectors.toList()
                )
        ));

System.out.println(doneByTeam.get("Backend").size());  // 1
System.out.println(doneByTeam.get("Frontend").size()); // 0
System.out.println(doneByTeam.containsKey("Frontend")); // true
System.out.println(doneByTeam.containsKey("QA"));       // false
```

Sự khác biệt không chỉ là hiệu năng; **đó là ngữ nghĩa của báo cáo**.

```text
Trước grouping:
  source → filter(done) → groupingBy(team)
                         Frontend không còn xuất hiện

Trong downstream:
  source → groupingBy(team, filtering(done, toList()))
                         Frontend được tạo với []
                         QA vẫn không tồn tại nếu không có Task nào
```

**Điều kiện:** dù có `Collectors.filtering`, classifier vẫn được gọi trước để tạo nhóm. Nó vẫn phải trả khóa không null. Do đó `filter(task -> task.team() != null)` hoặc bước chuẩn hóa khóa vẫn cần có nếu nguồn cho phép team null.

### Với counting cũng vậy

```java
Map<String, Long> doneCounts = tasks.stream()
        .filter(task -> task.team() != null)
        .collect(Collectors.groupingBy(
                Task::team,
                Collectors.filtering(
                        Task::done,
                        Collectors.counting()
                )
        ));

System.out.println(doneCounts.get("Backend"));  // 1
System.out.println(doneCounts.get("Frontend")); // 0
System.out.println(doneCounts.containsKey("QA")); // false
```

Ở đây `Frontend → 0L` là một mục có thật trong Map. Đây là giá trị khác với việc không có khóa QA.

### Phương án cho Java 8

Java 8 **không có** `Collectors.filtering`. Nếu muốn giữ nhóm rỗng khi không có phần tử khớp điều kiện, có thể nhóm tất cả các Task đã có khóa hợp lệ trước, rồi lọc từng danh sách:

```java
Map<String, List<Task>> allGroups = tasks.stream()
        .filter(task -> task.team() != null)
        .collect(Collectors.groupingBy(Task::team));

Map<String, List<Task>> doneGroups = new java.util.HashMap<>();

for (Map.Entry<String, List<Task>> entry : allGroups.entrySet()) {
    List<Task> doneTasks = entry.getValue().stream()
            .filter(Task::done)
            .collect(Collectors.toList());
    doneGroups.put(entry.getKey(), doneTasks);
}

System.out.println(doneGroups.containsKey("Frontend")); // true
System.out.println(doneGroups.get("Frontend").isEmpty()); // true
```

Đây là cách dễ hiểu nhưng cần danh sách trung gian cho từng nhóm và phải duyệt lại để lọc. Khi có Java 9+, `Collectors.filtering` thường trực tiếp hơn.

## 10. partitioningBy: luôn có hai khóa true và false

`Collectors.partitioningBy(predicate)` giải một bài toán đặc biệt: phân chia theo **một điều kiện boolean**. Kết quả có hai khóa `Boolean.TRUE` và `Boolean.FALSE`, **kể cả khi một nhánh không có phần tử**.

```java
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

List<Integer> scores = Arrays.asList(70, 85, 92);

Map<Boolean, List<Integer>> partitions = scores.stream()
        .collect(Collectors.partitioningBy(score -> score >= 50));

System.out.println(partitions.get(true));   // [70, 85, 92]
System.out.println(partitions.get(false));  // []
System.out.println(partitions.containsKey(false)); // true
```

Ngay cả Stream **hoàn toàn rỗng**, collector phân hoạch vẫn trả về hai mục:

```java
Map<Boolean, List<Integer>> emptyPartitions =
        java.util.stream.Stream.<Integer>empty()
                .collect(Collectors.partitioningBy(n -> n > 0));

System.out.println(emptyPartitions.size());      // 2
System.out.println(emptyPartitions.get(true));   // []
System.out.println(emptyPartitions.get(false));  // []
```

Ngược lại, `groupingBy` với classifier kiểu Boolean **không bảo đảm hai khóa** khi một nhánh không có phần tử:

```java
Map<Boolean, List<Integer>> groupedBoolean = scores.stream()
        .collect(Collectors.groupingBy(score -> score >= 50));

System.out.println(groupedBoolean.containsKey(true));  // true
System.out.println(groupedBoolean.containsKey(false)); // false
```

`groupingBy` chỉ tạo nhóm có dữ liệu, còn `partitioningBy` có hợp đồng **đúng hai phân hoạch**, mỗi phân hoạch mang kết quả downstream của nó.

### partitioningBy với downstream counting

```java
Map<Boolean, Long> countsByPassing = scores.stream()
        .collect(Collectors.partitioningBy(
                score -> score >= 50,
                Collectors.counting()
        ));

System.out.println(countsByPassing.get(true));  // 3
System.out.println(countsByPassing.get(false)); // 0
```

Nếu nguồn rỗng, cả hai phân hoạch có giá trị `0L`. Bộ đếm zero của phân hoạch không phải một key bị thiếu.

**Giới hạn:** `partitioningBy` chỉ áp dụng được khi bài toán tự nhiên là **hai nhánh** của cùng một predicate. Nếu cần ba hay nhiều nhóm như Backend, Frontend, QA, phải dùng `groupingBy` và chủ động bổ sung nhóm thiếu nếu cần.

## 11. Phân nhóm lồng nhau: nhóm ngoài có thể tồn tại khi nhóm trong thiếu

Một báo cáo có thể cần phân nhóm theo team rồi theo trạng thái. Ở cấp nhóm trong, việc vắng một trạng thái cũng làm mất khóa tương ứng.

Ví dụ:

```java
Map<String, Map<Boolean, List<Task>>> nestedGrouping = tasks.stream()
        .filter(task -> task.team() != null)
        .collect(Collectors.groupingBy(
                Task::team,
                Collectors.groupingBy(Task::done)
        ));

System.out.println(
        nestedGrouping.get("Frontend").containsKey(false)
); // true

System.out.println(
        nestedGrouping.get("Frontend").containsKey(true)
); // false
```

Nếu yêu cầu mỗi team xuất hiện cả hai trạng thái `true` và `false`, hãy thay downstream `groupingBy(Task::done)` bằng `partitioningBy(Task::done)`:

```java
Map<String, Map<Boolean, List<Task>>> nestedPartition = tasks.stream()
        .filter(task -> task.team() != null)
        .collect(Collectors.groupingBy(
                Task::team,
                Collectors.partitioningBy(Task::done)
        ));

System.out.println(nestedPartition.get("Frontend").get(true));  // []
System.out.println(nestedPartition.get("Frontend").get(false).size()); // 1
```

Điều này **chỉ bổ sung hai phân hoạch bên trong những team đã xuất hiện**. Team QA vẫn không có trong Map ngoài. Muốn QA xuất hiện, cần có danh sách team dự kiến và một bước bổ sung khóa ngoài như phần 8.

## 12. Parallel stream, groupingByConcurrent và vấn đề thứ tự

Khi dùng `parallelStream()`, `groupingBy` thông thường có thể tạo nhiều Map trung gian rồi gộp. `groupingByConcurrent` cung cấp một Collector **concurrent và unordered**, có thể phù hợp khi chỉ cần nhóm theo khóa và không quan tâm encounter order.

```java
import java.util.concurrent.ConcurrentMap;

ConcurrentMap<String, Long> concurrentCounts = tasks.parallelStream()
        .filter(task -> task.team() != null)
        .collect(Collectors.groupingByConcurrent(
                Task::team,
                Collectors.counting()
        ));

System.out.println(concurrentCounts.get("Backend")); // 2
```

Một số nguyên tắc phải giữ:

- `groupingByConcurrent` **không cho phép classifier trả null**; vẫn phải lọc, chuẩn hóa hoặc chuyển sang khóa Optional không null.
- Các khóa không có phần tử vẫn **không tự xuất hiện**.
- Collector là `UNORDERED`, vì thế nếu downstream tạo List, **thứ tự của phần tử trong mỗi nhóm không được cam kết** như khi thu thập có encounter order.
- `ConcurrentMap` không có nghĩa mọi `List` hoặc object mutable bên trong map đều tự an toàn để sửa đồng thời **sau** khi collect.
- Không suy luận parallel/concurrent luôn nhanh hơn: phân bố khóa, mức tranh chấp, chi phí kết hợp và kích thước nguồn quyết định hiệu năng.

Nếu báo cáo cần giữ thứ tự công việc theo ngày hoặc thứ tự nhập, nên xác định rõ khóa sắp xếp và dùng collector/order thích hợp, hoặc sắp xếp có quy tắc sau khi thu thập. Đừng dựa vào thứ tự duyệt không được API cam kết.

## 13. Xử lý thiếu khóa và thiếu nhóm khi thống kê

Với `Collectors.counting`, `summingLong`, `averagingInt` hay `mapping`, việc một nhóm không xuất hiện có nghĩa **không có bất kỳ phần tử nào tạo nhóm đó**. Còn nếu nhóm được tạo trước nhưng downstream lọc hết, giá trị mặc định của downstream là một kết quả riêng:

| Tình huống | Kết quả ví dụ | Có `containsKey`? |
| --- | --- | --- |
| Không có Task nào thuộc QA | `get("QA") == null` | Không |
| Có Frontend, downstream lọc tất cả Task | `get("Frontend").isEmpty()` | Có |
| Có Frontend, downstream `filtering` rồi `counting` | `get("Frontend") == 0L` | Có |
| `partitioningBy` không có phần tử thỏa predicate | `get(true).isEmpty()` | Có |
| `partitioningBy(..., counting())` trên Stream rỗng | `get(true) == 0L` và `get(false) == 0L` | Có cho cả hai |
| Key là `Optional.empty()` | Nhóm chứa các Task chưa có team | Có, nếu đã gặp Task có team null |

**Đừng dùng giá trị mặc định để suy ra dữ liệu gốc đã tồn tại.** Ví dụ `summingLong` có thể trả 0 vì tổng các giá trị dương/âm triệt tiêu nhau, chứ không nhất thiết vì nhóm rỗng. Tương tự, `getOrDefault` có thể che giấu việc khóa thật sự không có trong Map nếu caller không kiểm tra `containsKey`.

Với báo cáo cần phân biệt ba trạng thái `MISSING`, `EMPTY`, `NON_EMPTY`, có thể thiết kế DTO hoặc enum báo cáo tường minh thay vì suy luận từ `null` và kích thước danh sách. Ví dụ `Map` rỗng hoàn toàn là một dữ kiện khác với Map có ba khóa, mỗi khóa chứa danh sách rỗng.

## 14. Vòng đời Stream và chi phí bộ nhớ

`groupingBy`, `partitioningBy` và các biến thể của chúng đều là **terminal collect**. Chúng tiêu thụ pipeline một lần; không được tái sử dụng cùng instance Stream sau khi collect.

Với nguồn giữ tài nguyên như `Files.lines`, `collect` **không tự đóng Stream nguồn**. Cần dùng `try-with-resources` ngay tại nơi sở hữu nguồn:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.Stream;

static Map<String, Long> countNonEmptyLinesByPrefix(Path path)
        throws IOException {
    try (Stream<String> lines = Files.lines(path)) {
        return lines
                .filter(line -> !line.isEmpty())
                .collect(Collectors.groupingBy(
                        line -> line.substring(0, 1),
                        Collectors.counting()
                ));
    }
}
```

Ví dụ giả định mỗi dòng không rỗng đều có ký tự đầu; việc `filter` ở đây tránh lỗi `substring(0, 1)` với chuỗi rỗng. Lỗi đọc phát sinh trong quá trình duyệt lazy có thể xuất hiện dưới dạng `UncheckedIOException`, và `try-with-resources` vẫn bảo đảm đóng Stream đã mở.

Nếu giữ toàn bộ phần tử trong `Map<K,List<T>>`, bộ nhớ có thể tăng gần theo số phần tử đầu vào, cộng thêm chi phí Map và các List. Khi chỉ cần số lượng/tổng, dùng downstream `counting`/`summingLong` sẽ tránh phải giữ toàn bộ bản ghi, nhưng vẫn có chi phí theo số nhóm. Khi phải bổ sung hàng nghìn nhóm dự kiến, cũng cần cân nhắc kích thước Map và số container rỗng.

## 15. Ví dụ tổng hợp: báo cáo team có cả nhóm chưa phân công và nhóm rỗng

Yêu cầu báo cáo:

- Công việc có `team == null` phải xuất hiện trong nhóm **Chưa phân công**.
- Các team Backend, Frontend, QA **đều phải có mặt**, kể cả khi không có công việc.
- Mỗi nhóm chỉ hiển thị công việc đã hoàn thành, nhưng **nhóm không biến mất** nếu không có công việc hoàn thành.
- Thứ tự trình bày phải cố định: Backend, Frontend, QA, Chưa phân công.

Ở đây sử dụng Java 9+ vì downstream `Collectors.filtering`:

```java
import java.util.Arrays;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

String unassigned = "[CHUA_PHAN_NHOM]"; // mã dành riêng, không trùng team thật
List<String> teamOrder = Arrays.asList(
        "Backend", "Frontend", "QA", unassigned
);

// tasks là danh sách Task được tạo ở phần 3.
Map<String, List<Task>> collected = tasks.stream()
        .collect(Collectors.groupingBy(
                task -> task.team() == null
                        ? unassigned
                        : task.team(),
                Collectors.filtering(
                        Task::done,
                        Collectors.toList()
                )
        ));

Map<String, List<Task>> report = new LinkedHashMap<>();

for (String team : teamOrder) {
    report.put(
            team,
            collected.getOrDefault(team, Collections.emptyList())
    );
}

System.out.println(report.get("Backend").size());  // 1
System.out.println(report.get("Frontend").size()); // 0
System.out.println(report.get("QA").size());       // 0
System.out.println(report.get(unassigned).size()); // 0
System.out.println(report.containsKey("QA"));      // true
```

Những điểm chính:

1. Classifier **không bao giờ trả null** nhờ khóa riêng cho công việc chưa phân nhóm.
2. `Collectors.filtering` giữ các nhóm đã quan sát được, dù nhóm đó không có công việc hoàn thành.
3. `LinkedHashMap` tạo báo cáo theo thứ tự mong muốn và bổ sung nhóm QA chưa từng xuất hiện ở nguồn.
4. `Collections.emptyList()` chỉ dùng làm giá trị đọc cho nhóm không có phần tử, không dùng để cập nhật bằng `add`.
5. Báo cáo chỉ có các nhóm trong `teamOrder`. Nếu nguồn chứa team hợp lệ khác, phải xác định chính sách hiển thị bổ sung hoặc coi đó là dữ liệu ngoài cấu hình.

Nếu cần một trường thống kê bổ sung như tổng số việc, tổng việc hoàn thành và số việc bị bỏ vì thiếu team, hãy thiết kế báo cáo hoặc downstream collector chứa đủ thông tin đó. Không nên dựa trên một `Map<String,List<Task>>` chỉ gồm Task đã hoàn thành để suy ngược tổng số Task ban đầu.

## 16. Lỗi thường gặp và cách khắc phục

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| `groupingBy(Task::team)` khi `team == null` | Ném `NullPointerException` | Lọc, thay bằng mã riêng hoặc nhóm theo `Optional.ofNullable` |
| Đổi `groupingBy` sang `HashMap::new` để nhận khóa null | Không giải quyết hợp đồng classifier của `groupingBy` | Đảm bảo classifier trả khóa không null |
| Chỉ lọc `Objects::nonNull` trên các Task | Vẫn có thể gặp khóa team null | Kiểm tra riêng `task.team() != null` |
| Bỏ Task chưa có team nhưng báo cáo cần thống kê chúng | Mất thông tin nghiệp vụ | Chọn chính sách giữ nhóm chưa phân công |
| Dùng chuỗi thay thế có thể trùng tên team thật | Gộp nhầm hai nhóm | Mã riêng, enum/kiểu khóa hoặc `Optional` |
| Dùng `groupingBy` rồi mong mọi team cấu hình có mặt | Nhóm không xuất hiện sẽ không có khóa | Bổ sung các khóa từ danh sách team dự kiến |
| `getOrDefault("QA", emptyList())` rồi tưởng Map đã có QA | Không có khóa mới | Dùng Map báo cáo mới hoặc `computeIfAbsent` |
| Lọc `done` trước `groupingBy` nhưng cần giữ nhóm chưa hoàn thành | Nhóm bị biến mất | Dùng downstream `Collectors.filtering` trên Java 9+ |
| Dùng `Collectors.filtering` và mong cả nhóm chưa từng xuất hiện được tạo | Downstream không tự biết khóa từ miền nghiệp vụ | Cung cấp danh sách khóa dự kiến |
| Dùng `groupingBy` theo Boolean và mong luôn có cả true/false | Nhánh chưa thấy phần tử bị thiếu | Dùng `partitioningBy` |
| Dùng `groupingByConcurrent` để giữ thứ tự phần tử trong nhóm | Collector unordered | Chọn collector/order phù hợp |
| Xem `0` là bằng chứng nhóm chưa có Task | Tổng số có thể bằng 0 do quy tắc số học | Kiểm tra `containsKey` và lưu đủ thống kê |
| Terminal `collect` xong nghĩ nguồn tệp đã đóng | Tài nguyên còn mở | Dùng `try-with-resources` |

## 17. Câu hỏi tự kiểm tra

1. `groupingBy` có chấp nhận classifier trả `null` khi dùng `HashMap::new` không? **Không**; nó vẫn ném `NullPointerException`.
2. `Optional.ofNullable(team)` giúp gì? **Tạo khóa Optional không null**; `Optional.empty()` biểu diễn team vắng mặt.
3. Khi không có Task thuộc QA, `groupingBy` có tạo `QA → []` không? **Không**; nó không tự sinh khóa QA.
4. `map.getOrDefault("QA", emptyList())` có tự thêm QA vào Map không? **Không**; chỉ trả danh sách dự phòng.
5. Vì sao lọc `Task::done` **trước** grouping khác `Collectors.filtering(Task::done, toList())` **bên trong** grouping? **Vì** lọc trước có thể loại mọi phần tử của nhóm khiến khóa biến mất, còn downstream giữ nhóm từng được phân loại.
6. `Collectors.filtering` có từ Java mấy? **Java 9**; trên Java 8 có thể nhóm rồi lọc các danh sách.
7. `partitioningBy` trên Stream rỗng trả mấy khóa? **Hai**: `true` và `false`, mỗi khóa có kết quả downstream rỗng.
8. `groupingBy(x -> predicate(x))` có luôn trả hai khóa Boolean không? **Không**; chỉ tạo khóa của nhánh đã có phần tử.
9. `groupingBy(team, partitioningBy(done))` có làm team chưa từng xuất hiện được thêm vào Map ngoài không? **Không**; nó chỉ đảm bảo hai phân hoạch **bên trong những team có dữ liệu**.
10. `groupingByConcurrent` có cho classifier trả null không? **Không**; và nó không cam kết encounter order.
11. Vì sao không nên coi danh sách rỗng và khóa không tồn tại là một trạng thái? **Vì** báo cáo có thể cần phân biệt nhóm đã quan sát nhưng không có phần tử hợp lệ với nhóm chưa hề xuất hiện.
12. Để luôn xuất Backend, Frontend, QA, cần bổ sung thông tin gì? **Danh sách các team dự kiến**, rồi tạo/bổ sung Map kết quả theo danh sách đó.

**Nguyên tắc áp dụng:** Hãy quyết định rõ **khóa thiếu dữ liệu được loại, báo lỗi hay đưa vào nhóm riêng**, và **nhóm không có phần tử cần biến mất hay được giữ với kết quả rỗng**. `groupingBy` không nhận khóa classifier null và không tự sinh nhóm chưa thấy; `partitioningBy` luôn cung cấp hai khóa Boolean; `Collectors.filtering` giữ nhóm đã quan sát được nhưng không tạo nhóm ngoài miền dữ liệu. Thiết kế đúng ngữ nghĩa trước rồi mới tối ưu song song, bộ nhớ và hiệu năng.
