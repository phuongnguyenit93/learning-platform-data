# Sử dụng SIZE, INDEX và các biểu thức cho tập hợp trong JPQL

Trong Java, khi làm việc với `List`, `Set` hoặc `Map`, ta thường gọi các phương thức quen thuộc như `size()`, `isEmpty()`, `contains()` và `get(index)`. Nhưng khi một tập hợp là **thuộc tính persistent của entity JPA**, việc cần làm thường không phải tải cả tập hợp vào Java rồi xử lý, mà là **đưa câu hỏi xuống database** bằng JPQL.

Ví dụ, hệ thống có các kế hoạch học tập (`LearningPlan`), mỗi kế hoạch chứa nhiều nhiệm vụ (`PlanTask`), một tập kỹ năng (`Set<String> skills`) và một Map cấu hình (`Map<String,String> settings`). Ta cần trả lời:

- Kế hoạch nào có **ít nhất 5 nhiệm vụ**?
- Kế hoạch nào **không có nhiệm vụ**?
- Nhiệm vụ nào nằm ở **vị trí thứ 3** trong danh sách có thứ tự?
- Kế hoạch nào chứa kỹ năng `"JPA"`?
- Kế hoạch nào có thiết lập `"difficulty" = "advanced"`?
- Làm sao đếm các nhiệm vụ ở trạng thái `DONE`, thay vì đếm tất cả?
- Khi nào dùng `SIZE`, `INDEX`, `IS EMPTY`, `MEMBER OF`, `KEY`/`VALUE` và khi nào dùng `JOIN`/`COUNT`/`EXISTS`?

JPQL có những biểu thức chuyên biệt giúp giải quyết các câu hỏi này:

| Biểu thức JPQL | Mục đích chính | Ví dụ |
| --- | --- | --- |
| `SIZE(collectionPath)` | Đếm số phần tử của tập hợp đã ánh xạ | `SIZE(p.tasks) >= 5` |
| `INDEX(elementAlias)` | Lấy vị trí của phần tử trong **List có thứ tự được lưu** | `INDEX(t) = 2` |
| `collectionPath IS EMPTY` | Kiểm tra collection không có phần tử | `p.tasks IS EMPTY` |
| `collectionPath IS NOT EMPTY` | Kiểm tra có ít nhất một phần tử | `p.skills IS NOT EMPTY` |
| `value MEMBER OF collectionPath` | Kiểm tra một giá trị/entity thuộc collection | `:skill MEMBER OF p.skills` |
| `value NOT MEMBER OF collectionPath` | Kiểm tra không thuộc collection | `:skill NOT MEMBER OF p.skills` |
| `KEY(mapAlias)` | Lấy key của entry trong Map | `KEY(s) = :key` |
| `VALUE(mapAlias)` | Lấy value của entry trong Map | `VALUE(s) = :value` |
| `ENTRY(mapAlias)` | Lấy một Map entry trong projection | `SELECT ENTRY(s)` |
| `JOIN collectionPath alias` | Duyệt từng phần tử và đặt điều kiện riêng | `JOIN p.tasks t` |

**Đặc biệt:** `SIZE` và `INDEX` **không giống nhau**. `SIZE(p.tasks)` là số lượng nhiệm vụ trong một kế hoạch; `INDEX(t)` là vị trí của **một phần tử cụ thể** trong danh sách của kế hoạch. Một cái áp dụng lên **đường dẫn collection**, cái còn lại áp dụng lên **bí danh phần tử List được join**.

Bài học trình bày cú pháp, cách ánh xạ entity, dữ liệu mẫu, kết quả dự kiến, cách dùng với `EntityManager`, những giới hạn về query semantics, hiệu năng và các tình huống thực tế.

## 1. Collection trong JPA khác collection thuần Java ở điểm nào?

Giả sử Java có:

```java
List<String> values = List.of("A", "B", "C");

System.out.println(values.size());     // 3
System.out.println(values.get(1));     // B
System.out.println(values.isEmpty());  // false
System.out.println(values.contains("C")); // true
```

Ở đây dữ liệu nằm sẵn trong bộ nhớ, nên Java trực tiếp thực hiện các thao tác.

Trong JPA, một entity có thể khai báo:

```java
@OneToMany(mappedBy = "plan", fetch = FetchType.LAZY)
private List<PlanTask> tasks = new ArrayList<>();
```

`tasks` là **persistent collection**. Nếu quan hệ được cấu hình `LAZY`, chưa chắc toàn bộ phần tử đã được nạp vào memory khi `LearningPlan` được tải.

Giả sử cần danh sách kế hoạch có từ 5 nhiệm vụ trở lên. Có hai cách tiếp cận:

**Cách không phù hợp khi dữ liệu lớn:** tải tất cả LearningPlan, truy cập từng `plan.getTasks()` rồi gọi `size()` trong Java. Điều này có thể khiến provider truy vấn thêm các collection, dẫn tới N+1 hoặc tải nhiều entity không cần thiết.

**Cách đặt điều kiện ở database:**

```jpql
SELECT p
FROM LearningPlan p
WHERE SIZE(p.tasks) >= :minimum
```

Provider chuyển biểu thức về SQL thích hợp để database kiểm tra số lượng phần tử. Ứng dụng không cần tự lặp từng kế hoạch rồi tải toàn bộ nhiệm vụ chỉ để biết nó có bao nhiêu phần tử.

> Các biểu thức JPQL làm việc trên **mô hình dữ liệu persistent** mà provider/database nhìn thấy. Chúng không phải lời gọi trực tiếp tới phương thức Java `List.size()`, `List.get()` hay `Set.contains()`.

## 2. Mô hình minh họa: LearningPlan, PlanTask, skills và settings

Ta dùng bốn thành phần:

- `LearningPlan`: entity gốc, có `id` và `name`.
- `PlanTask`: entity con, có `id`, `title`, `status` và thuộc một plan.
- `LearningPlan.tasks`: **`List<PlanTask>` có `@OrderColumn`** để lưu vị trí.
- `LearningPlan.skills` và `settings`: hai **`@ElementCollection`** chứa giá trị cơ bản và các cặp key/value.

Sơ đồ:

```text
                       LearningPlan#10
                      +------------------+
                      | name = "JPA Core"|
                      +------------------+
                        |       |       |
        tasks (List) ---+       |       +--- settings (Map)
        có @OrderColumn         |            "level" -> "advanced"
                               |
                           skills (Set)
                         {"Java", "JPA"}

               tasks:
               index 0 -> PlanTask#101 "Mapping"
               index 1 -> PlanTask#102 "JPQL"
               index 2 -> PlanTask#103 "Transactions"
```

Mô hình này giúp thấy rõ:

- **`SIZE(p.tasks)`** đếm số nhiệm vụ: 3.
- **`INDEX(t)`** với `t = PlanTask#102` trả 1.
- **`"JPA" MEMBER OF p.skills`** kiểm tra membership.
- **`KEY(s)`** và **`VALUE(s)`** cho phép truy vấn entry của settings Map.

### 2.1. Schema quan hệ

DDL PostgreSQL minh họa:

```sql
CREATE TABLE learning_plans (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name VARCHAR(160) NOT NULL,
    version BIGINT NOT NULL
);

CREATE TABLE plan_tasks (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    plan_id BIGINT NOT NULL REFERENCES learning_plans(id),
    position_idx INTEGER,
    title VARCHAR(200) NOT NULL,
    status VARCHAR(16) NOT NULL
);

CREATE TABLE plan_skills (
    plan_id BIGINT NOT NULL REFERENCES learning_plans(id),
    skill VARCHAR(80) NOT NULL,
    PRIMARY KEY (plan_id, skill)
);

CREATE TABLE plan_settings (
    plan_id BIGINT NOT NULL REFERENCES learning_plans(id),
    setting_key VARCHAR(80) NOT NULL,
    setting_value VARCHAR(200),
    PRIMARY KEY (plan_id, setting_key)
);
```

`position_idx` là **cột thứ tự do `@OrderColumn` quản lý**. Nó không phải khóa chính của `PlanTask`; khóa chính vẫn là `id`.

Ở ví dụ DDL, `position_idx` được để nullable để không phụ thuộc giả định rằng provider phải ghi vị trí ngay trong lần INSERT đầu tiên. Sau khi flush thành công, các vị trí trong List được JPA quản lý theo mapping. Nếu muốn ràng buộc `NOT NULL` hoặc `UNIQUE(plan_id, position_idx)`, cần kiểm tra chiến lược INSERT/UPDATE/reorder của provider và migration thực tế.

`PlanTask` có primary key độc lập. Collection skills và settings không có entity riêng cho từng `String` hoặc entry Map.

### 2.2. Entity LearningPlan

```java
package com.example.learning;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import jakarta.persistence.*;

@Entity
@Table(name = "learning_plans")
public class LearningPlan {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 160)
    private String name;

    @Version
    @Column(nullable = false)
    private Long version;

    @OneToMany(
        mappedBy = "plan",
        fetch = FetchType.LAZY,
        cascade = {
            CascadeType.PERSIST,
            CascadeType.MERGE,
            CascadeType.REMOVE
        },
        orphanRemoval = true
    )
    @OrderColumn(name = "position_idx")
    private List<PlanTask> tasks = new ArrayList<>();

    @ElementCollection(fetch = FetchType.LAZY)
    @CollectionTable(
        name = "plan_skills",
        joinColumns = @JoinColumn(name = "plan_id")
    )
    @Column(name = "skill", nullable = false, length = 80)
    private Set<String> skills = new HashSet<>();

    @ElementCollection(fetch = FetchType.LAZY)
    @CollectionTable(
        name = "plan_settings",
        joinColumns = @JoinColumn(name = "plan_id")
    )
    @MapKeyColumn(name = "setting_key", length = 80)
    @Column(name = "setting_value", length = 200)
    private Map<String, String> settings = new HashMap<>();

    protected LearningPlan() {
    }

    public LearningPlan(String name) {
        this.name = Objects.requireNonNull(name);
    }

    public void addTask(PlanTask task) {
        Objects.requireNonNull(task);
        if (task.getPlan() != null) {
            throw new IllegalArgumentException(
                "Task already belongs to a plan"
            );
        }
        tasks.add(task);
        task.assignPlan(this);
    }

    public void addSkill(String skill) {
        skills.add(Objects.requireNonNull(skill));
    }

    public void setSetting(String key, String value) {
        settings.put(Objects.requireNonNull(key), value);
    }

    public Long getId() { return id; }
    public String getName() { return name; }
    public Long getVersion() { return version; }

    public List<PlanTask> getTasks() { return tasks; }
    public Set<String> getSkills() { return skills; }
    public Map<String, String> getSettings() { return settings; }
}
```

Một số điểm quan trọng:

1. `tasks` là `List` có `@OrderColumn`. JPA lưu chỉ số phần tử, cho phép biểu thức `INDEX(t)` khi join List.
2. `skills` là `Set<String>`. Nó có membership và size, nhưng không có vị trí thứ 0, thứ 1 như List.
3. `settings` là `Map<String,String>`. Khóa Map không phải chỉ số List; truy vấn key bằng `KEY`, không bằng `INDEX`.
4. `orphanRemoval = true` và các cascade chỉ là lựa chọn vòng đời trong ví dụ. Chúng **không quyết định cách `SIZE` hoặc `INDEX` hoạt động**.
5. `@Version` minh họa cách ứng dụng kiểm soát sửa đổi đồng thời; nó không thay thế row-level ordering hoặc mọi điều kiện ràng buộc của collection.

### 2.3. Entity PlanTask

```java
package com.example.learning;

import jakarta.persistence.*;

@Entity
@Table(name = "plan_tasks")
public class PlanTask {

    public enum Status {
        TODO, DONE
    }

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "plan_id", nullable = false)
    private LearningPlan plan;

    @Column(nullable = false, length = 200)
    private String title;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 16)
    private Status status = Status.TODO;

    protected PlanTask() {
    }

    public PlanTask(String title) {
        this.title = title;
    }

    void assignPlan(LearningPlan plan) {
        this.plan = plan;
    }

    public Long getId() { return id; }
    public LearningPlan getPlan() { return plan; }
    public String getTitle() { return title; }
    public Status getStatus() { return status; }

    public void complete() {
        status = Status.DONE;
    }
}
```

`PlanTask` **không khai báo thuộc tính Java `positionIdx`** vì vị trí nằm trong annotation `@OrderColumn` trên collection của LearningPlan. Trong JPQL, muốn truy cập vị trí này theo nghĩa thứ tự List, dùng `INDEX(t)` sau khi join `p.tasks t`.

### 2.4. Tập dữ liệu mẫu

Giả sử các hàng sau đã được persist và commit:

| Plan | name | Tasks theo thứ tự | Skills | Settings |
| --- | --- | --- | --- | --- |
| 10 | JPA Core | 101 Mapping, 102 JPQL, 103 Transactions | Java, JPA | level=advanced, language=vi |
| 20 | Java Web | 201 Servlet, 202 REST | Java, HTTP | level=intermediate |
| 30 | New Plan | *(rỗng)* | *(rỗng)* | *(rỗng)* |
| 40 | SQL Practice | 401 SELECT, 402 JOIN, 403 GROUP BY, 404 Index | SQL, Database | level=advanced |

Vị trí List bắt đầu từ **0**:

| plan_id | task_id | position_idx | title |
| ---: | ---: | ---: | --- |
| 10 | 101 | 0 | Mapping |
| 10 | 102 | 1 | JPQL |
| 10 | 103 | 2 | Transactions |
| 20 | 201 | 0 | Servlet |
| 20 | 202 | 1 | REST |
| 40 | 401 | 0 | SELECT |
| 40 | 402 | 1 | JOIN |
| 40 | 403 | 2 | GROUP BY |
| 40 | 404 | 3 | Index |

Các ví dụ bên dưới thường dựa trên dữ liệu mẫu này. Việc tự chèn dữ liệu SQL tường minh có ID trong database dùng identity generator chỉ phục vụ minh họa; ứng dụng thật nên persist entity rồi để JPA cấp khóa và quản lý vị trí.

## 3. SIZE(collectionPath): lấy số phần tử

Cú pháp:

```jpql
SIZE(collection_valued_path_expression)
```

Ví dụ:

```jpql
SELECT p
FROM LearningPlan p
WHERE SIZE(p.tasks) >= 3
```

Ý nghĩa: chọn LearningPlan có **ít nhất 3 phần tử** trong collection `tasks`.

Theo dữ liệu mẫu, kết quả gồm:

- LearningPlan#10 (3 tasks).
- LearningPlan#40 (4 tasks).

LearningPlan#20 có 2 tasks, #30 có 0, nên bị loại.

### 3.1. SIZE trả về giá trị số

`SIZE(p.tasks)` biểu thị một giá trị số nguyên, do đó có thể dùng với phép so sánh:

```jpql
WHERE SIZE(p.tasks) = 0
WHERE SIZE(p.tasks) > 0
WHERE SIZE(p.tasks) >= :minimum
WHERE SIZE(p.tasks) BETWEEN :min AND :max
```

Ví dụ tham số:

```java
List<LearningPlan> plans = em.createQuery(
        "SELECT p FROM LearningPlan p " +
        "WHERE SIZE(p.tasks) >= :minimum",
        LearningPlan.class
    )
    .setParameter("minimum", 3)
    .getResultList();
```

**Không viết `p.tasks.size()` trong JPQL** như thể JPQL là Java source code. Cú pháp là hàm `SIZE(...)`, không phải gọi instance method.

### 3.2. SIZE trên Set hoặc collection giá trị

`skills` là `Set<String>`:

```jpql
SELECT p
FROM LearningPlan p
WHERE SIZE(p.skills) >= 2
```

Với dữ liệu mẫu, #10, #20 và #40 đều có ít nhất 2 skills.

`SIZE` hoạt động trên **collection-valued persistent path**; phần tử có thể là entity như `PlanTask` hoặc kiểu giá trị như `String` trong `@ElementCollection`.

Trong những mapping/phạm vi phiên bản cho phép Map-valued collections, `SIZE(p.settings)` có ý nghĩa số entry Map. Tuy nhiên, đối với những use case portability hoặc provider khác nhau, cần xác nhận khả năng xử lý Map path theo đúng Jakarta Persistence version mà ứng dụng sử dụng.

### 3.3. SIZE cho collection rỗng

Khi collection không có phần tử, `SIZE` trả **0**.

```jpql
SELECT p
FROM LearningPlan p
WHERE SIZE(p.tasks) = 0
```

Theo dữ liệu mẫu, truy vấn trả `LearningPlan#30`.

Vì trong database, một collection quan hệ rỗng thường được biểu diễn bằng **không có hàng liên kết**, không phải một cột SQL chứa `NULL`, nên về mặt JPQL **empty collection khác null reference**.

### 3.4. SIZE trong SELECT

`SIZE` không chỉ dùng trong WHERE:

```jpql
SELECT p.id, p.name, SIZE(p.tasks)
FROM LearningPlan p
ORDER BY p.id
```

Kết quả ý tưởng:

| p.id | p.name | SIZE(p.tasks) |
| ---: | --- | ---: |
| 10 | JPA Core | 3 |
| 20 | Java Web | 2 |
| 30 | New Plan | 0 |
| 40 | SQL Practice | 4 |

Java nhận scalar tuples:

```java
List<Object[]> rows = em.createQuery(
        "SELECT p.id, p.name, SIZE(p.tasks) " +
        "FROM LearningPlan p ORDER BY p.id",
        Object[].class
    )
    .getResultList();

for (Object[] row : rows) {
    Long id = (Long) row[0];
    String name = (String) row[1];
    Integer taskCount = (Integer) row[2];

    System.out.println(id + " | " + name + " | " + taskCount);
}
```

Nếu dữ liệu được trả về từ một provider cụ thể khác lớp numeric dự kiến, cần đối chiếu kiểu kết quả với hợp đồng hàm `SIZE`/JPA provider. Trong mapping JPA thông dụng, `SIZE` là giá trị nguyên.

### 3.5. DTO projection dùng SIZE

Giả sử DTO:

```java
package com.example.learning.dto;

public record PlanSizeSummary(
    Long planId,
    String planName,
    Integer taskCount
) {}
```

Query:

```jpql
SELECT new com.example.learning.dto.PlanSizeSummary(
    p.id,
    p.name,
    SIZE(p.tasks)
)
FROM LearningPlan p
```

DTO projection hữu ích khi màn hình chỉ cần ID, tên và số lượng nhiệm vụ. Ta không cần tải collection `tasks` thành các entity chỉ để hiển thị con số.

### 3.6. Có nên ORDER BY SIZE?

Khi muốn xếp kế hoạch theo số nhiệm vụ, có thể dùng scalar result variable:

```jpql
SELECT p.id, p.name, SIZE(p.tasks) AS taskCount
FROM LearningPlan p
ORDER BY taskCount DESC, p.id ASC
```

Khả năng hỗ trợ một số cách viết biểu thức trong `ORDER BY` tùy phiên bản JPQL/provider; sử dụng một biểu thức đã chọn với result variable như `taskCount` giúp ý định rõ ràng. Nếu truy vấn phải portable giữa provider, nên xác nhận trên provider mục tiêu.

## 4. SIZE được thực thi như thế nào ở database?

JPQL làm việc với collection đã ánh xạ, nhưng database quan hệ lưu quan hệ trong bảng con hoặc bảng liên kết. Với `LearningPlan.tasks`, một cách SQL tương đương là correlated subquery:

```sql
SELECT p.*
FROM learning_plans p
WHERE (
    SELECT COUNT(*)
    FROM plan_tasks t
    WHERE t.plan_id = p.id
) >= ?;
```

Hoặc SQL query optimizer/provider có thể dùng hình thức JOIN, GROUP BY hoặc subquery khác.

**Không có yêu cầu rằng `SIZE(p.tasks)` nhất thiết phát đúng một câu `SELECT COUNT(*)` lồng như ví dụ**. Hình dạng SQL tùy provider, mapping, phiên bản và database dialect.

Nhưng về semantics:

- Provider cần xác định **số phần tử persistent** liên quan tới mỗi plan.
- Không cần khởi tạo `p.getTasks()` trong Java để trả lời điều kiện.
- Nếu dùng `SIZE` cho nhiều plan, database có thể phải đếm nhiều nhóm hàng; hiệu năng phụ thuộc index, thống kê và query plan.

### 4.1. Index hỗ trợ SIZE

Nếu bảng con chứa `plan_id`, thường nên cân nhắc:

```sql
CREATE INDEX idx_plan_tasks_plan
ON plan_tasks(plan_id);
```

Index có thể giúp database đếm/lọc các tasks theo plan. Nhưng có index không phải bảo đảm mọi `SIZE` query đều nhanh: với tập dữ liệu lớn, nhiều plan và bộ lọc phức tạp, optimizer có thể chọn kế hoạch khác.

### 4.2. SIZE không phải lúc nào cũng là phép đo “không có chi phí”

Một query:

```jpql
SELECT p
FROM LearningPlan p
WHERE SIZE(p.tasks) > 1000
```

có thể đòi hỏi database xác định số task của nhiều plan. Nếu chạy thường xuyên trên hàng triệu task, cần đo SQL, phân tích index và cân nhắc thống kê/tối ưu theo workload.

Đừng gọi `SIZE` trong hàng loạt query chỉ vì nó ngắn; hãy hỏi có thực sự cần **đếm chính xác toàn bộ** hay chỉ cần biết **tồn tại ít nhất một phần tử**.

## 5. IS EMPTY và IS NOT EMPTY

JPQL có hai dạng đặc biệt cho collection:

```jpql
collectionPath IS EMPTY
collectionPath IS NOT EMPTY
```

Ví dụ:

```jpql
SELECT p
FROM LearningPlan p
WHERE p.tasks IS EMPTY
```

Trả các plan không có task, ở dữ liệu mẫu là `LearningPlan#30`.

Tương đương về mục tiêu nghiệp vụ với:

```jpql
WHERE SIZE(p.tasks) = 0
```

Để tìm plan có ít nhất một task:

```jpql
SELECT p
FROM LearningPlan p
WHERE p.tasks IS NOT EMPTY
```

Điều này tương ứng mục tiêu với `SIZE(p.tasks) > 0`.

### 5.1. Khi nào ưu tiên IS EMPTY?

Nếu bài toán chỉ hỏi “tập hợp có rỗng không?”, `IS EMPTY` biểu đạt ý định trực tiếp hơn:

```jpql
WHERE p.tasks IS EMPTY
```

Database có thể xử lý bằng `NOT EXISTS` hoặc một kế hoạch khác, không nhất thiết phải đếm mọi phần tử. Nhưng không khẳng định `IS EMPTY` luôn nhanh hơn `SIZE(...) = 0` trong mọi DBMS/provider; cần kiểm tra execution plan thực tế.

### 5.2. Null của collection và empty không giống null của association đơn trị

Quan hệ tùy chọn:

```java
@ManyToOne
private Customer reviewer;
```

có thể được kiểm tra bằng:

```jpql
WHERE p.reviewer IS NULL
```

Nhưng với collection `p.tasks`, muốn biết không có task nên dùng:

```jpql
WHERE p.tasks IS EMPTY
```

Không nên diễn đạt câu hỏi “không có con” bằng `p.tasks IS NULL`. Một persistent collection thường biểu diễn **nhiều hoặc không có phần tử**, không phải một association đơn trị nullable.

## 6. MEMBER OF: kiểm tra phần tử có thuộc collection không?

Cú pháp:

```jpql
value MEMBER OF collectionPath
value NOT MEMBER OF collectionPath
```

Từ khóa `OF` đôi khi có thể được viết theo biến thể cú pháp được hỗ trợ, nhưng nên dùng đầy đủ `MEMBER OF` và `NOT MEMBER OF` để dễ đọc.

### 6.1. Với Set<String> skills

```jpql
SELECT p
FROM LearningPlan p
WHERE :skill MEMBER OF p.skills
```

Tham số:

```java
List<LearningPlan> plans = em.createQuery(
        "SELECT p FROM LearningPlan p " +
        "WHERE :skill MEMBER OF p.skills",
        LearningPlan.class
    )
    .setParameter("skill", "JPA")
    .getResultList();
```

Với dữ liệu mẫu, kết quả gồm `LearningPlan#10`.

Ta không phải tải `skills` của tất cả plan rồi chạy `getSkills().contains("JPA")`. Membership được biểu diễn ở database dựa trên collection table.

### 6.2. Với collection entity PlanTask

```jpql
SELECT p
FROM LearningPlan p
WHERE :task MEMBER OF p.tasks
```

Khi truyền tham số `:task`, nên dùng một `PlanTask` có danh tính JPA hợp lệ và đang được quản lý/trong ngữ cảnh phù hợp.

```java
PlanTask task = em.find(PlanTask.class, taskId);

if (task == null) {
    return List.of();
}

List<LearningPlan> owners = em.createQuery(
        "SELECT p FROM LearningPlan p " +
        "WHERE :task MEMBER OF p.tasks",
        LearningPlan.class
    )
    .setParameter("task", task)
    .getResultList();
```

Đối với mô hình `PlanTask.plan` bắt buộc và một task chỉ thuộc một plan, thông thường có tối đa một owner phù hợp.

Nếu chỉ biết ID và không muốn nạp task, có thể diễn đạt bằng JOIN:

```jpql
SELECT DISTINCT p
FROM LearningPlan p
JOIN p.tasks t
WHERE t.id = :taskId
```

Cách này không đòi hỏi một entity parameter `PlanTask`.

### 6.3. NOT MEMBER OF

Tìm những plan **không chứa kỹ năng JPA**:

```jpql
SELECT p
FROM LearningPlan p
WHERE :skill NOT MEMBER OF p.skills
```

Với `:skill = "JPA"`, các plan #20, #30, #40 thỏa điều kiện trong dữ liệu mẫu.

Lưu ý semantic của `MEMBER OF` khi một vế null/unknown có thể chịu logic ba giá trị; ứng dụng nên có chính sách rõ ràng cho tham số `null` thay vì kỳ vọng null giống chuỗi rỗng hoặc một kỹ năng cụ thể. Với tập hợp rỗng, không có phần tử khớp, nên membership không đúng.

### 6.4. MEMBER OF và JOIN có thể thay thế nhau ở mục tiêu nào?

Hai cách tìm plan có skill `"JPA"`:

**MEMBER OF:**

```jpql
SELECT p
FROM LearningPlan p
WHERE :skill MEMBER OF p.skills
```

**JOIN:**

```jpql
SELECT DISTINCT p
FROM LearningPlan p
JOIN p.skills s
WHERE s = :skill
```

Về mục tiêu, cả hai hỏi “có ít nhất một skill bằng giá trị này”. Nhưng cách diễn đạt khác:

- `MEMBER OF` phù hợp khi chỉ cần kiểm tra **membership**.
- `JOIN` phù hợp khi cần dùng **bí danh phần tử** cho nhiều điều kiện, projection hay aggregate.

Cần phân biệt xử lý duplicate và ngữ nghĩa null khi kết hợp thêm joins hoặc điều kiện khác; hai query trên tương đương trong trường hợp cơ bản của `Set<String>` mẫu.

## 7. INDEX(elementAlias): vị trí phần tử trong List được lưu thứ tự

`INDEX` dùng trong JPQL để đọc **vị trí của phần tử trong một List có thứ tự được ánh xạ**, chẳng hạn:

```java
@OneToMany(mappedBy = "plan")
@OrderColumn(name = "position_idx")
private List<PlanTask> tasks;
```

Ở đây `@OrderColumn` là mấu chốt: nó yêu cầu provider lưu và duy trì **chỉ số thứ tự** của List.

Muốn lấy task ở vị trí 2 (phần tử thứ 3), viết:

```jpql
SELECT t
FROM LearningPlan p
JOIN p.tasks t
WHERE p.id = :planId
  AND INDEX(t) = :position
```

Dùng:

```java
List<PlanTask> tasks = em.createQuery(
        "SELECT t FROM LearningPlan p " +
        "JOIN p.tasks t " +
        "WHERE p.id = :planId " +
        "AND INDEX(t) = :position",
        PlanTask.class
    )
    .setParameter("planId", 10L)
    .setParameter("position", 2)
    .getResultList();
```

Theo dữ liệu mẫu, kết quả là `PlanTask#103 "Transactions"`.

### 7.1. INDEX áp dụng lên alias, không áp dụng lên toàn collection

Đúng:

```jpql
FROM LearningPlan p
JOIN p.tasks t
WHERE INDEX(t) = 0
```

Không đúng cú pháp mục tiêu:

```jpql
WHERE INDEX(p.tasks) = 0
```

`INDEX(t)` ở đây hỏi **vị trí của một phần tử `t` trong List được join**. `p.tasks` là đường dẫn collection, không phải một phần tử cụ thể có vị trí duy nhất.

### 7.2. Vị trí bắt đầu từ 0

Với List được JPA quản lý bằng `@OrderColumn`:

```text
Java List index         INDEX(t) trong JPQL
----------------       -------------------
0                      0
1                      1
2                      2
3                      3
```

Ví dụ:

```java
plan.getTasks().get(0)
```

tương ứng **về mặt vị trí** với task có `INDEX(t) = 0` trong query trên plan, khi dữ liệu đã được đồng bộ và mapping đúng.

Nếu giao diện người dùng đánh số “bước 1, bước 2, bước 3”, cần đổi:

```text
UI number = INDEX + 1
```

Đừng nhầm “nhiệm vụ thứ 3” với `INDEX(t) = 3`; nó phải bằng 2.

### 7.3. INDEX không phải khóa chính entity

Giả sử `PlanTask#103` ở index 2. Nếu người dùng kéo nhiệm vụ này lên đầu danh sách:

```text
Trước:
0 -> Task#101
1 -> Task#102
2 -> Task#103

Sau:
0 -> Task#103
1 -> Task#101
2 -> Task#102
```

Entity vẫn là **Task#103**, nhưng `INDEX(t)` đổi từ 2 thành 0. Vì vậy:

- `Task.id` là entity identity.
- `INDEX(t)` là **vị trí hiện tại trong danh sách của owner**.
- Không dùng index làm ID bền vững cho REST API hoặc foreign key.
- Nếu List có thể reorder, các bookmark/URL chỉ dựa trên index sẽ trỏ sang phần tử khác sau khi sắp xếp lại.

### 7.4. INDEX trong SELECT

```jpql
SELECT t, INDEX(t)
FROM LearningPlan p
JOIN p.tasks t
WHERE p.id = :planId
ORDER BY INDEX(t)
```

Kết quả mẫu cho plan #10:

| Task | INDEX(t) |
| --- | ---: |
| Task#101 Mapping | 0 |
| Task#102 JPQL | 1 |
| Task#103 Transactions | 2 |

Đoạn Java:

```java
List<Object[]> rows = em.createQuery(
        "SELECT t, INDEX(t) " +
        "FROM LearningPlan p JOIN p.tasks t " +
        "WHERE p.id = :planId " +
        "ORDER BY INDEX(t)",
        Object[].class
    )
    .setParameter("planId", 10L)
    .getResultList();

for (Object[] row : rows) {
    PlanTask task = (PlanTask) row[0];
    Integer position = (Integer) row[1];

    System.out.println(position + ": " + task.getTitle());
}
```

Query trả `PlanTask` và vị trí tương ứng mà không bắt buộc gọi `getTasks().get(i)` trên managed plan.

### 7.5. INDEX trong WHERE và ORDER BY

Ví dụ chọn các task từ vị trí 1 trở đi:

```jpql
SELECT t
FROM LearningPlan p
JOIN p.tasks t
WHERE p.id = :planId
  AND INDEX(t) >= :start
ORDER BY INDEX(t)
```

Hoặc chọn một khoảng vị trí:

```jpql
WHERE INDEX(t) BETWEEN :first AND :last
```

Cần hiểu `INDEX(t)` làm việc trên **vị trí đã lưu trong database mà transaction thấy**; nó không tự phản ánh một thao tác đổi vị trí chỉ xảy ra trong một detached List chưa đồng bộ.

### 7.6. INDEX không tương đương @OrderBy

JPA có hai annotation rất dễ nhầm:

- **`@OrderColumn`**: lưu thứ tự vật lý của các phần tử trong List bằng một cột do provider quản lý; phù hợp với biểu thức `INDEX`.
- **`@OrderBy`**: chỉ định thứ tự đọc dựa trên thuộc tính của entity/embeddable, ví dụ `title ASC`; không tự tạo một cột vị trí `0,1,2,...`.

Ví dụ:

```java
@OneToMany(mappedBy = "plan")
@OrderBy("title ASC")
private List<PlanTask> tasks;
```

Dù Java trả một `List`, mapping này **không cung cấp cùng cơ chế persistent index của `@OrderColumn`**. Không được kỳ vọng `INDEX(t)` portable trên List chỉ có `@OrderBy`.

Nếu chỉ cần hiển thị theo tiêu đề, dùng `@OrderBy` hoặc `ORDER BY t.title`. Nếu nghiệp vụ cần kéo-thả và lưu thứ tự tùy ý, cần `@OrderColumn` hoặc một trường vị trí được mô hình hóa tường minh.

### 7.7. INDEX không áp dụng cho Set

`Set<String> skills` không có phần tử thứ nhất/thứ hai theo hợp đồng thứ tự `Set` mặc định.

Đây không phải ý định hợp lệ:

```jpql
-- Không dùng INDEX cho Set:
SELECT INDEX(s)
FROM LearningPlan p JOIN p.skills s
```

Nếu nghiệp vụ cần thứ tự bền vững, phải chọn một mô hình có thứ tự lưu rõ ràng, ví dụ `List` với `@OrderColumn`.

### 7.8. INDEX không áp dụng cho Map key

Với `Map<String,String> settings`, lấy khóa bằng `KEY(s)`, không phải `INDEX(s)`:

```jpql
SELECT KEY(s), VALUE(s)
FROM LearningPlan p
JOIN p.settings s
```

Map key là thành phần định danh một entry trong Map theo mapping; không phải vị trí 0-based của List.

## 8. Khi List thay đổi, INDEX thay đổi như thế nào?

Giả sử plan #10 có ba task:

```text
0: Mapping
1: JPQL
2: Transactions
```

Trong transaction, mã Java thực hiện:

```java
LearningPlan plan = em.find(LearningPlan.class, 10L);

PlanTask moved = plan.getTasks().remove(2);
plan.getTasks().add(0, moved);
```

Sau khi provider đồng bộ thành công, vị trí có thể trở thành:

```text
0: Transactions
1: Mapping
2: JPQL
```

Điều này có thể gây **nhiều UPDATE** trên cột thứ tự, không chỉ trên phần tử được kéo.

### 8.1. INDEX có thể đòi hỏi cập nhật nhiều hàng

Nếu danh sách chứa 10.000 phần tử và chèn một task vào đầu, JPA có thể phải đánh lại vị trí của nhiều hàng. Vì vậy, `@OrderColumn` thuận tiện về semantics nhưng có thể tốn chi phí khi reorder thường xuyên.

Với các danh sách lớn được kéo-thả liên tục, đôi khi cần một thiết kế vị trí riêng như số thứ tự thưa (*sparse rank*), khóa sắp xếp hoặc thứ tự do domain quản lý; những thiết kế đó **không còn tương đương tự động với `INDEX` chuẩn của `@OrderColumn`**.

### 8.2. Ràng buộc uniqueness khi reorder

Một schema có:

```sql
UNIQUE (plan_id, position_idx)
```

giúp ngăn hai task cùng có vị trí trong một plan. Tuy nhiên, một số chiến lược UPDATE vị trí có thể tạm thời tạo trùng trước khi hoàn tất reorder, tùy database/provider. Nếu áp unique constraint, cần kiểm tra cách provider thực thi thay đổi thứ tự và khả năng dùng ràng buộc deferred/chiến lược cập nhật phù hợp.

**Không nên chỉ thêm unique index rồi giả định mọi thao tác `list.add(0, ...)` và `list.remove(...)` luôn vượt constraint trên mọi DBMS.**

### 8.3. Concurrency khi hai người cùng reorder

Nếu hai transaction đọc cùng một thứ tự rồi cùng di chuyển các task, có thể xảy ra lost update hoặc xung đột vị trí. `@Version` trên LearningPlan có thể hỗ trợ trong một số kiểu cập nhật collection, nhưng hành vi tăng version theo collection mapping/provider cần được xác nhận; không nên coi nó là bảo đảm tuyệt đối với mọi writer ngoài JPA.

Nếu thứ tự mang ý nghĩa nghiệp vụ quan trọng, có thể cần locking ở plan hoặc một cơ chế cập nhật thứ tự có điều kiện trong transaction.

## 9. KEY, VALUE và ENTRY cho Map-valued association

Map là collection có đặc trưng **key → value**. JPA cho phép ánh xạ Map bằng `@ElementCollection` hoặc các association phù hợp.

Trong ví dụ:

```java
@ElementCollection
@CollectionTable(
    name = "plan_settings",
    joinColumns = @JoinColumn(name = "plan_id")
)
@MapKeyColumn(name = "setting_key")
@Column(name = "setting_value")
private Map<String, String> settings = new HashMap<>();
```

Dữ liệu:

| plan_id | setting_key | setting_value |
| ---: | --- | --- |
| 10 | level | advanced |
| 10 | language | vi |
| 20 | level | intermediate |
| 40 | level | advanced |

### 9.1. JOIN Map và dùng KEY()

```jpql
SELECT p
FROM LearningPlan p
JOIN p.settings s
WHERE KEY(s) = :key
```

Với `:key = "language"`, truy vấn tìm plan có một setting mang key `language` — trong dữ liệu mẫu là plan #10.

### 9.2. VALUE() là giá trị Map

```jpql
SELECT p
FROM LearningPlan p
JOIN p.settings s
WHERE KEY(s) = :key
  AND VALUE(s) = :value
```

Với `:key = "level"` và `:value = "advanced"`, kết quả là #10 và #40.

Một số provider có thể cho dùng alias Map entry như value trực tiếp trong ngữ cảnh nhất định; nhưng `KEY(s)` và `VALUE(s)` biểu đạt rõ ý định và phù hợp khi dạy JPQL nâng cao.

### 9.3. ENTRY() trong SELECT

```jpql
SELECT ENTRY(s)
FROM LearningPlan p
JOIN p.settings s
WHERE p.id = :planId
```

`ENTRY(s)` chọn entry của Map — một cặp key/value — chứ không phải entity `LearningPlan`.

Kết quả thường được xử lý theo cấu trúc entry phù hợp của JPA, ví dụ `Map.Entry` cho projection được hỗ trợ:

```java
List<?> entries = em.createQuery(
        "SELECT ENTRY(s) " +
        "FROM LearningPlan p JOIN p.settings s " +
        "WHERE p.id = :planId"
    )
    .setParameter("planId", 10L)
    .getResultList();

for (Object entry : entries) {
    System.out.println(entry);
}
```

Nếu chỉ cần dữ liệu scalar để hiển thị, `SELECT KEY(s), VALUE(s)` với `Object[]` hoặc DTO có thể tiện hơn. Một số giới hạn của `ENTRY` trong các vị trí khác `SELECT` được quy định theo phiên bản JPQL/provider; không suy luận `ENTRY(s)` dùng như alias entity ở mọi mệnh đề.

### 9.4. Map của entity

Nếu một plan có:

```java
@OneToMany(mappedBy = "plan")
@MapKey(name = "code")
private Map<String, PlanTask> tasksByCode;
```

và `PlanTask` được bổ sung thuộc tính persistent `code`, thì:

```jpql
SELECT t
FROM LearningPlan p
JOIN p.tasksByCode t
WHERE KEY(t) = :code
```

`t` vẫn là entity `PlanTask` có `@Id`, còn `KEY(t)` là khóa Map. `@MapKey(name = "code")` dùng thuộc tính của entity làm key; khác với `@MapKeyColumn` lưu key vào cột riêng của collection table.

Đây là **biến thể mapping**, không cần tạo trùng class PlanTask hoặc áp đồng thời cả hai collection `tasks` và `tasksByCode` vào một entity cụ thể nếu domain không yêu cầu. Các ví dụ chính vẫn dùng `List<PlanTask> tasks`.

## 10. IS EMPTY và MEMBER OF trên các collection khác nhau

Các biểu thức cho collection không đồng nghĩa phải dùng cùng một kiểu Java. Một hệ thống có thể lưu:

```java
@ElementCollection
private Set<String> tags;

@OneToMany
private List<PlanTask> tasks;

@ManyToMany
private Set<Course> courses;
```

Các phép kiểm tra:

```jpql
WHERE p.tags IS EMPTY
WHERE p.tasks IS NOT EMPTY
WHERE :course MEMBER OF p.courses
```

đều dựa trên **collection-valued paths** đã ánh xạ.

Nhưng:

- `SIZE` đếm số phần tử.
- `IS EMPTY` kiểm tra có phần tử hay không.
- `MEMBER OF` kiểm tra một phần tử cụ thể.
- `INDEX` chỉ áp dụng khi có ngữ nghĩa ordered List index.
- `KEY`/`VALUE` thuộc Map join, không phải Set/List bình thường.

Không chọn hàm chỉ theo cú pháp ngắn, mà chọn theo **kiểu collection và câu hỏi nghiệp vụ**.

### 10.1. Tập hợp entity và giá trị khác nhau ở tham số MEMBER OF

Với basic collection:

```jpql
:skill MEMBER OF p.skills
```

Tham số thường là `String`.

Với entity collection:

```jpql
:task MEMBER OF p.tasks
```

Tham số là một entity `PlanTask` có identity. Nếu chỉ có ID và không cần object, `JOIN ... WHERE t.id = :id` hoặc `EXISTS` có thể rõ ràng và tránh phải dựng entity parameter.

### 10.2. Nếu collection là Set thì thứ tự hiển thị ở đâu?

`Set` diễn đạt uniqueness theo `equals()/hashCode()`, không đảm bảo thứ tự truy cập theo vị trí. Nếu cần hiển thị skills theo thứ tự alphabet, dùng `ORDER BY` trong query trên phần tử hoặc sắp xếp ở tầng trình bày:

```jpql
SELECT s
FROM LearningPlan p
JOIN p.skills s
WHERE p.id = :planId
ORDER BY s
```

Đừng dùng `INDEX(s)` với `Set<String>`.

## 11. SIZE khác COUNT khi JOIN collection

Hai cách đếm task là:

**SIZE trực tiếp theo owner:**

```jpql
SELECT p.id, SIZE(p.tasks)
FROM LearningPlan p
```

**JOIN và COUNT theo group:**

```jpql
SELECT p.id, COUNT(t)
FROM LearningPlan p
LEFT JOIN p.tasks t
GROUP BY p.id
```

Trong ví dụ cơ bản, cả hai có thể trả số lượng task giống nhau.

Tuy nhiên, chúng khác nhau về **hình thức query** và tính linh hoạt.

| Tiêu chí | SIZE | JOIN + COUNT |
| --- | --- | --- |
| Biểu diễn số phần tử của một collection | Rất trực tiếp | Cần JOIN và aggregate |
| Đếm theo điều kiện trên child | Không có tham số predicate nội bộ | Dùng `JOIN ... ON` hoặc WHERE/HAVING phù hợp |
| Giữ parent có 0 child | SIZE trả 0 | Cần `LEFT JOIN` nếu muốn giữ parent |
| Kết hợp nhiều aggregate khác nhau | Có thể cồng kềnh | GROUP BY/CASE/subquery linh hoạt hơn |
| Nguy cơ nhân bản do join nhiều collection | Không phụ thuộc outer JOIN trong câu hỏi đơn giản | Cần chú ý số hàng và DISTINCT |

### 11.1. Đếm đúng tất cả tasks bằng LEFT JOIN

```jpql
SELECT p.id, p.name, COUNT(t)
FROM LearningPlan p
LEFT JOIN p.tasks t
GROUP BY p.id, p.name
ORDER BY p.id
```

Đối với plan #30 không có task, `COUNT(t)` trả 0 vì `t` là null trên hàng left join không khớp.

Nếu viết inner join:

```jpql
FROM LearningPlan p
JOIN p.tasks t
```

thì plan #30 không còn hàng trong kết quả để GROUP BY.

### 11.2. SIZE luôn tính toàn bộ collection đang được xét

`SIZE(p.tasks)` không có đối số như “chỉ đếm task DONE”. Nếu cần:

> Mỗi plan có bao nhiêu task `DONE`?

dùng JOIN có điều kiện:

```jpql
SELECT p.id, COUNT(t)
FROM LearningPlan p
LEFT JOIN p.tasks t ON t.status = :done
GROUP BY p.id
```

Với dữ liệu status phù hợp, plan không có task DONE vẫn xuất hiện và có count 0.

Nếu thay `ON t.status = :done` bằng `WHERE t.status = :done` sau LEFT JOIN, những plan không có task DONE có thể bị loại, không còn count 0. Đây là khác biệt quan trọng giữa lọc **phần tử tham gia join** và lọc **các hàng kết quả**.

### 11.3. COUNT(DISTINCT t) khi có nhiều joins

Nếu cùng query join `p.tasks` và `p.skills`:

```jpql
SELECT p.id, COUNT(t)
FROM LearningPlan p
JOIN p.tasks t
JOIN p.skills s
GROUP BY p.id
```

một plan có 3 tasks và 2 skills có thể tạo 6 hàng join. `COUNT(t)` khi đó trả 6, không phải 3.

Để đếm entity task duy nhất:

```jpql
SELECT p.id, COUNT(DISTINCT t)
FROM LearningPlan p
JOIN p.tasks t
JOIN p.skills s
GROUP BY p.id
```

Nhưng inner join vào skills vẫn loại plan không có skill. Nếu muốn giữ mọi plan, cần xét LEFT JOIN, câu query aggregate riêng hoặc subquery. Không dùng `DISTINCT` như một công tắc chữa mọi sai lệch của mô hình join.

## 12. EXISTS: kiểm tra có phần tử thỏa điều kiện

Giả sử yêu cầu:

> Kế hoạch nào có ít nhất một nhiệm vụ DONE?

`SIZE(p.tasks) > 0` không đủ, vì nó đếm cả TODO. `MEMBER OF` cũng không thích hợp khi không biết trước entity task cụ thể.

Có thể dùng `EXISTS`:

```jpql
SELECT p
FROM LearningPlan p
WHERE EXISTS (
    SELECT t.id
    FROM PlanTask t
    WHERE t.plan = p
      AND t.status = :done
)
```

Hoặc JOIN:

```jpql
SELECT DISTINCT p
FROM LearningPlan p
JOIN p.tasks t
WHERE t.status = :done
```

Hai cách có mục tiêu tương tự. `EXISTS` hữu ích khi chỉ cần biết **có một phần tử thỏa**, không cần chọn trường child và muốn tránh nhân root rows trong FROM của query chính.

### 12.1. NOT EXISTS khác với SIZE = 0

```jpql
WHERE SIZE(p.tasks) = 0
```

có nghĩa **không có nhiệm vụ nào**.

```jpql
WHERE NOT EXISTS (
    SELECT t.id
    FROM PlanTask t
    WHERE t.plan = p AND t.status = :done
)
```

có nghĩa **không có nhiệm vụ DONE**, nhưng plan vẫn có thể có rất nhiều task TODO.

Đừng thay một điều kiện bằng điều kiện kia chỉ vì đều có cụm từ “không có”.

### 12.2. Đếm có điều kiện bằng subquery trong WHERE

Muốn tìm plan có ít nhất 2 nhiệm vụ DONE:

```jpql
SELECT p
FROM LearningPlan p
WHERE (
    SELECT COUNT(t)
    FROM PlanTask t
    WHERE t.plan = p
      AND t.status = :done
) >= :minimum
```

Hoặc một truy vấn JOIN/GROUP BY/HAVING phù hợp:

```jpql
SELECT p
FROM LearningPlan p
JOIN p.tasks t
WHERE t.status = :done
GROUP BY p
HAVING COUNT(t) >= :minimum
```

Với `GROUP BY p`, khả năng hỗ trợ group entity và chi tiết SQL có thể khác giữa provider/phiên bản, đặc biệt khi entity có nhiều field LOB/eager relationships; nếu cần portable hơn, có thể group theo khóa của entity rồi query ID hoặc projection phù hợp.

**Ý chính:** `SIZE` rất thuận tiện cho **tổng số phần tử**; COUNT/HAVING/EXISTS linh hoạt hơn khi có điều kiện trên từng phần tử.

## 13. IS EMPTY có thể diễn đạt bằng NOT EXISTS

Hai query:

```jpql
SELECT p FROM LearningPlan p
WHERE p.tasks IS EMPTY
```

và:

```jpql
SELECT p FROM LearningPlan p
WHERE NOT EXISTS (
    SELECT t.id
    FROM PlanTask t
    WHERE t.plan = p
)
```

đều diễn đạt mục tiêu tìm plan không có task.

SQL thường có thể dùng:

```sql
SELECT p.*
FROM learning_plans p
WHERE NOT EXISTS (
    SELECT 1
    FROM plan_tasks t
    WHERE t.plan_id = p.id
);
```

Đây là mô hình SQL minh họa. Không phải mọi provider sẽ tạo đúng truy vấn này từ `IS EMPTY`.

### 13.1. Khi nào chọn cách nào?

- **`IS EMPTY`:** ngắn gọn, dễ hiểu khi chỉ kiểm tra rỗng.
- **`NOT EXISTS`:** hữu ích khi cần bổ sung điều kiện của child, ví dụ “không có task DONE” hoặc “không có task quá hạn”.

Nếu truy vấn chỉ cần biết có tồn tại ít nhất một phần tử và không cần count chính xác, `EXISTS`/`IS NOT EMPTY` có thể để optimizer tối ưu theo hướng dừng sớm. Nhưng không tuyên bố một cú pháp luôn nhanh hơn cú pháp khác.

## 14. Truy cập field phần tử phải qua JOIN, không qua collection path

`LearningPlan.tasks` là một collection-valued path. Không thể đi tiếp bằng dấu chấm như một entity đơn:

```jpql
-- Không hợp lệ theo ý nghĩa collection navigation:
SELECT p
FROM LearningPlan p
WHERE p.tasks.status = :done
```

Thay bằng:

```jpql
SELECT DISTINCT p
FROM LearningPlan p
JOIN p.tasks t
WHERE t.status = :done
```

Hoặc `EXISTS` như ở phần trước.

Đây là điểm phân biệt:

| Câu hỏi | Cách diễn đạt |
| --- | --- |
| Bao nhiêu task? | `SIZE(p.tasks)` |
| Có task nào không? | `p.tasks IS NOT EMPTY` |
| Task cụ thể có trong plan không? | `:task MEMBER OF p.tasks` |
| Task ở index 2 là gì? | `JOIN p.tasks t WHERE INDEX(t) = 2` |
| Có task DONE không? | `JOIN ... WHERE t.status = DONE` hoặc `EXISTS` |
| Có bao nhiêu task DONE? | `JOIN/COUNT` hoặc subquery COUNT |
| Lấy tên từng task | `JOIN p.tasks t SELECT t.title` |

Không dùng `SIZE` để tìm field từng phần tử, cũng không dùng `INDEX` để đếm cả collection.

## 15. INDEX và số lượng phần tử không nhất thiết cùng một quy tắc nghiệp vụ

Giả sử một plan có 3 task:

```text
index 0 -> Task A
index 1 -> Task B
index 2 -> Task C
```

Lúc đó:

```jpql
SIZE(p.tasks) = 3
```

và index lớn nhất là 2.

Tuy nhiên, không nên viết logic nghiệp vụ suy ra **Task cuối luôn có `INDEX = SIZE - 1`** trong mọi thời điểm không kiểm soát:

- Collection có thể đang bị thay đổi trong memory chưa flush.
- Dữ liệu SQL bên ngoài JPA có thể làm hỏng vị trí hoặc tạo gap.
- Query có thể chịu transaction isolation/auto-flush.
- List có thể bị reorder đồng thời.
- Provider/database có thể áp dụng ràng buộc/thứ tự khác khi mapping không đúng.

Trong một ordered List hợp lệ đã đồng bộ đầy đủ, các vị trí thường liền nhau từ 0 theo `@OrderColumn`. Nhưng **index là thuộc tính thứ tự có thể thay đổi**, không phải quy tắc định danh của task.

### 15.1. Tìm task cuối cùng trong List

Một cách có thể diễn đạt:

```jpql
SELECT t
FROM LearningPlan p
JOIN p.tasks t
WHERE p.id = :planId
  AND INDEX(t) = SIZE(p.tasks) - 1
```

Về ý tưởng, nó chọn phần tử cuối trong List có thứ tự hợp lệ. Tuy nhiên, không phải mọi provider đều tối ưu biểu thức kết hợp INDEX và SIZE giống nhau; nếu portability hoặc hiệu năng là ưu tiên, có thể truy vấn các vị trí theo `ORDER BY INDEX(t) DESC` rồi `setMaxResults(1)` trong context phù hợp.

Nhớ xử lý trường hợp List rỗng: không có task nào ở index -1, nên kết quả sẽ rỗng.

### 15.2. Tìm phần tử ở vị trí đầu

```jpql
SELECT t
FROM LearningPlan p
JOIN p.tasks t
WHERE p.id = :planId
  AND INDEX(t) = 0
```

Truy vấn này **không** yêu cầu thứ tự alphabet hay thời điểm tạo task; nó lấy phần tử ở vị trí đầu của List đã được persist.

## 16. Collection rỗng và ba giá trị logic

Một số biểu thức JPQL tuân thủ logic null/unknown của SQL. Điều đó đặc biệt quan trọng khi truy vấn tham số nullable hoặc dùng LEFT JOIN.

Ví dụ:

```jpql
SELECT p
FROM LearningPlan p
LEFT JOIN p.tasks t
WHERE t.status <> :done
```

Truy vấn không có nghĩa là “plan không có task DONE”. Với plan không có task, `t` có thể null; `t.status <> :done` không nhận giá trị TRUE. Với plan có cả TODO và DONE, chỉ cần một hàng TODO là plan có thể xuất hiện dù cũng có task DONE.

Muốn đúng câu hỏi **“không có task DONE”**, dùng:

```jpql
SELECT p
FROM LearningPlan p
WHERE NOT EXISTS (
    SELECT t.id FROM PlanTask t
    WHERE t.plan = p
      AND t.status = :done
)
```

Còn muốn **“không có task nào”**, dùng:

```jpql
WHERE p.tasks IS EMPTY
```

### 16.1. MEMBER OF với null

Nếu gọi:

```java
query.setParameter("skill", null);
```

với điều kiện `:skill MEMBER OF p.skills`, kết quả phụ thuộc vào quy tắc null/unknown của biểu thức, không nên coi nó tương đương membership một chuỗi rỗng.

Ứng dụng nên chuẩn hóa/validate tham số:

```java
if (skill == null || skill.isBlank()) {
    throw new IllegalArgumentException("Skill is required");
}
```

Cách này tránh làm logic tìm kiếm phụ thuộc vào trường hợp đặc biệt không có nghĩa vụ nghiệp vụ rõ ràng.

## 17. Truy vấn Map: key tồn tại, value bằng và số entry

Giả sử settings có `level → advanced` và `language → vi`.

Tìm plan có setting key `language`:

```jpql
SELECT DISTINCT p
FROM LearningPlan p
JOIN p.settings s
WHERE KEY(s) = :key
```

Tìm plan có đúng cặp key/value:

```jpql
SELECT DISTINCT p
FROM LearningPlan p
JOIN p.settings s
WHERE KEY(s) = :key
  AND VALUE(s) = :value
```

Tìm tất cả key/value của một plan:

```jpql
SELECT KEY(s), VALUE(s)
FROM LearningPlan p
JOIN p.settings s
WHERE p.id = :planId
```

Đừng nhầm `KEY(s)` với `INDEX(s)`:

- `KEY` dành cho Map entry.
- `INDEX` dành cho ordered List element.
- `SIZE` trả số phần tử/entry ở collection path theo mapping.
- `MEMBER OF` không phải cách chung để kiểm tra Map key; JOIN Map và `KEY` là rõ nhất.

### 17.1. Những entry Map có value null

Khi `setting_value` nullable, query:

```jpql
WHERE VALUE(s) = :value
```

không dùng so sánh bằng để tìm null. Để tìm entry có value null, dùng:

```jpql
SELECT p
FROM LearningPlan p
JOIN p.settings s
WHERE VALUE(s) IS NULL
```

Cần phân biệt **Map không có key** với **Map có key nhưng value null**. Nếu cần phân biệt cụ thể, lọc bằng `KEY(s) = :key` rồi xem `VALUE(s)`; không suy từ một phép so sánh bằng null.

## 18. Criteria API tương ứng với SIZE và INDEX

JPQL phù hợp cho nhiều query viết bằng chuỗi. Khi muốn xây dựng truy vấn có type-checking từ API hoặc bộ lọc động, JPA Criteria API có các khái niệm tương ứng.

### 18.1. CriteriaBuilder.size

Ví dụ thiết lập query chọn plan có ít nhất ba tasks:

```java
import jakarta.persistence.criteria.CriteriaBuilder;
import jakarta.persistence.criteria.CriteriaQuery;
import jakarta.persistence.criteria.Root;

CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<LearningPlan> cq =
    cb.createQuery(LearningPlan.class);

Root<LearningPlan> plan = cq.from(LearningPlan.class);

cq.select(plan)
  .where(cb.ge(cb.size(plan.get("tasks")), 3));

List<LearningPlan> results =
    em.createQuery(cq).getResultList();
```

Đây là ý tưởng tương ứng với:

```jpql
SELECT p
FROM LearningPlan p
WHERE SIZE(p.tasks) >= 3
```

Trong dự án sử dụng static metamodel, có thể thay `"tasks"` bằng thuộc tính metamodel để giảm lỗi gõ chuỗi. Kiểu generic của Criteria API có thể cần khai báo rõ theo phiên bản JPA/compiler nếu mapping phức tạp.

### 18.2. CriteriaBuilder.isEmpty và isNotEmpty

Ý tưởng:

```java
cq.select(plan)
  .where(cb.isEmpty(plan.get("tasks")));
```

tương ứng:

```jpql
WHERE p.tasks IS EMPTY
```

Tương tự, `cb.isNotEmpty(...)` cho `IS NOT EMPTY`.

### 18.3. CriteriaBuilder.isMember

```java
cq.select(plan)
  .where(cb.isMember("JPA", plan.get("skills")));
```

tương ứng:

```jpql
WHERE 'JPA' MEMBER OF p.skills
```

Khi dùng tham số động, có thể tạo `ParameterExpression<String>` rồi truyền với `setParameter` thay vì hardcode.

### 18.4. ListJoin.index()

Với Criteria API, `ListJoin` có phương thức `index()`:

```java
import jakarta.persistence.criteria.CriteriaQuery;
import jakarta.persistence.criteria.CriteriaBuilder;
import jakarta.persistence.criteria.ListJoin;
import jakarta.persistence.criteria.Root;
import jakarta.persistence.Tuple;

CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<Tuple> cq = cb.createTupleQuery();

Root<LearningPlan> plan = cq.from(LearningPlan.class);
ListJoin<LearningPlan, PlanTask> task =
    plan.joinList("tasks");

cq.multiselect(
      task.alias("task"),
      task.index().alias("position")
  )
  .where(cb.equal(plan.get("id"), 10L))
  .orderBy(cb.asc(task.index()));

List<Tuple> rows = em.createQuery(cq).getResultList();
```

Đây là phiên bản Criteria của:

```jpql
SELECT t, INDEX(t)
FROM LearningPlan p
JOIN p.tasks t
WHERE p.id = 10
ORDER BY INDEX(t)
```

Để code hoạt động, List cần mapping có ngữ nghĩa position phù hợp, ví dụ `@OrderColumn` đã khai báo.

### 18.5. MapJoin.key/value/entry

Criteria API còn hỗ trợ `MapJoin` cho association/element collection kiểu Map. Ý tưởng:

```java
var settingsJoin = plan.joinMap("settings");

cq.multiselect(
    settingsJoin.key(),
    settingsJoin.value()
);
```

Đây là ví dụ **cách xây biểu thức**. Khi tích hợp vào một CriteriaQuery cụ thể, cần xác định kiểu kết quả và aliases phù hợp với `multiselect`. Không dùng `ListJoin.index()` để đọc key của Map.

## 19. Auto-flush và trạng thái collection đang thay đổi

Một câu hỏi thường gặp:

> Nếu vừa `plan.getTasks().add(task)` trong transaction, `SIZE(p.tasks)` có đếm ngay phần tử mới không?

Câu trả lời phải dựa vào **trạng thái persistent và flush mode**, không chỉ nhìn List Java.

Ví dụ:

```java
LearningPlan plan = em.find(LearningPlan.class, 10L);

plan.addTask(new PlanTask("Criteria API"));

Integer count = em.createQuery(
        "SELECT SIZE(p.tasks) FROM LearningPlan p " +
        "WHERE p.id = :id",
        Integer.class
    )
    .setParameter("id", 10L)
    .getSingleResult();
```

Nếu truy vấn chạy trong transaction với `FlushModeType.AUTO`, provider có thể cần flush những thay đổi liên quan để bảo đảm ngữ nghĩa query theo hợp đồng JPA. Khi đó count có thể bao gồm task mới, tùy việc cascade persist và đồng bộ diễn ra hợp lệ.

Nếu chưa flush hoặc code đang dùng detached entity/transaction không phù hợp, không được mặc định rằng query luôn phản ánh mọi thay đổi chỉ nằm trong Java memory.

**Phân biệt:**

- `plan.getTasks().size()`: số lượng của Java collection ở object mà ứng dụng đang giữ, có thể khởi tạo lazy collection.
- `SELECT SIZE(p.tasks)`: số lượng theo semantics persistent collection mà JPA query phải biểu diễn; có thể thực thi SQL, chịu flush/isolation.
- `SELECT COUNT(t) FROM ... JOIN ...`: một biểu thức aggregate trên các hàng join của query.

Đừng dùng hai kết quả này như một cơ chế kiểm tra đồng bộ dữ liệu mà không hiểu transaction và auto-flush.

## 20. FetchType.LAZY và N+1

Tập hợp `tasks` trong ví dụ có:

```java
@OneToMany(fetch = FetchType.LAZY, ...)
private List<PlanTask> tasks;
```

Nếu làm:

```java
List<LearningPlan> plans = em.createQuery(
    "SELECT p FROM LearningPlan p",
    LearningPlan.class
).getResultList();

for (LearningPlan plan : plans) {
    System.out.println(plan.getTasks().size());
}
```

provider có thể phải thực hiện thêm các truy vấn để xử lý những collection chưa khởi tạo, tùy khả năng tối ưu, cache và provider. Với nhiều plans, nguy cơ **N+1** xuất hiện.

Nếu chỉ cần số lượng, projection trực tiếp:

```jpql
SELECT p.id, SIZE(p.tasks)
FROM LearningPlan p
```

thường diễn đạt yêu cầu tốt hơn việc tải các entity và duyệt collection ở Java.

Tuy nhiên, **không bảo đảm mỗi lần dùng SIZE chỉ có đúng một SQL cho mọi provider**; cần quan sát SQL thực tế nếu tối ưu là mục tiêu quan trọng.

### 20.1. SIZE không phải JOIN FETCH

`SIZE(p.tasks)` trả số lượng; nó **không yêu cầu provider tải toàn bộ tasks vào collection của managed LearningPlan**.

`JOIN FETCH p.tasks` lại yêu cầu load association, kéo theo các PlanTask và có thể tạo nhiều hàng SQL cho mỗi plan.

Nếu màn hình cần đúng danh sách task cùng tiêu đề và trạng thái, fetch join hoặc DTO query có thể thích hợp. Nếu chỉ cần một con số, `SIZE`/COUNT aggregate thường phù hợp hơn.

### 20.2. Không dùng fetch join collection để chỉ đếm

Một truy vấn:

```jpql
SELECT DISTINCT p
FROM LearningPlan p
LEFT JOIN FETCH p.tasks
```

sẽ hướng tới việc tải tasks, không phải một phép count nhẹ. Với số lượng plan và task lớn, chi phí memory/SQL có thể cao.

**Chọn phép truy vấn theo dữ liệu cần trả về**, không theo thói quen dùng fetch join để tránh mọi vấn đề lazy.

## 21. INDEX, ORDER BY và phân trang

Giả sử cần đọc 10 task đầu trong một plan, giữ đúng thứ tự đã cấu hình bằng `@OrderColumn`:

```jpql
SELECT t
FROM LearningPlan p
JOIN p.tasks t
WHERE p.id = :planId
ORDER BY INDEX(t)
```

Java:

```java
List<PlanTask> firstTen = em.createQuery(
        "SELECT t FROM LearningPlan p " +
        "JOIN p.tasks t " +
        "WHERE p.id = :id " +
        "ORDER BY INDEX(t)",
        PlanTask.class
    )
    .setParameter("id", planId)
    .setFirstResult(0)
    .setMaxResults(10)
    .getResultList();
```

Ở đây `SELECT t` chọn **PlanTask**, tức mỗi kết quả là một phần tử List, không phải nhiều plan gốc bị nhân bản. Phân trang theo task có thể hợp lý hơn việc fetch collection của nhiều parent rồi áp LIMIT cho parent.

### 21.1. Nếu cần khoảng vị trí cố định

```jpql
SELECT t
FROM LearningPlan p
JOIN p.tasks t
WHERE p.id = :planId
  AND INDEX(t) BETWEEN :start AND :end
ORDER BY INDEX(t)
```

Với khoảng vị trí từ 10 đến 19, truy vấn yêu cầu các phần tử có index nằm trong khoảng đó.

Điều này khác với offset pagination nếu List có gap bất thường hoặc dữ liệu đang thay đổi đồng thời. Khi có reorder, hai request phân trang có thể thấy phần tử bị dịch chuyển; cần thiết kế consistency/locking nếu nghiệp vụ bắt buộc một snapshot thứ tự ổn định.

### 21.2. Đừng dùng vị trí làm định danh REST API

Endpoint:

```text
GET /plans/10/tasks/2
```

có thể được hiểu là lấy task ở **position=2**, nhưng nếu người dùng reorder, URL không còn trỏ cùng task. Nếu client cần một tài nguyên ổn định, dùng:

```text
GET /tasks/103
```

và có thể trả thêm `position` trong DTO. `INDEX` thuộc **thứ tự hiển thị tại thời điểm truy vấn**, không phải entity identity.

## 22. Ví dụ đa điều kiện: plans thỏa tất cả yêu cầu

Một màn hình tìm kiếm cho phép người dùng lọc kế hoạch theo:

- Có ít nhất `minimumTasks` nhiệm vụ.
- Chứa kỹ năng `requiredSkill`.
- Có `level = "advanced"`.
- Không có task DONE.

Truy vấn có thể là:

```jpql
SELECT DISTINCT p
FROM LearningPlan p
JOIN p.settings s
WHERE SIZE(p.tasks) >= :minimumTasks
  AND :requiredSkill MEMBER OF p.skills
  AND KEY(s) = :settingKey
  AND VALUE(s) = :settingValue
  AND NOT EXISTS (
      SELECT t.id
      FROM PlanTask t
      WHERE t.plan = p
        AND t.status = :done
  )
```

Java:

```java
List<LearningPlan> matching = em.createQuery(
        "SELECT DISTINCT p FROM LearningPlan p " +
        "JOIN p.settings s " +
        "WHERE SIZE(p.tasks) >= :minimumTasks " +
        "AND :requiredSkill MEMBER OF p.skills " +
        "AND KEY(s) = :settingKey " +
        "AND VALUE(s) = :settingValue " +
        "AND NOT EXISTS (" +
        " SELECT t.id FROM PlanTask t " +
        " WHERE t.plan = p AND t.status = :done)",
        LearningPlan.class
    )
    .setParameter("minimumTasks", 3)
    .setParameter("requiredSkill", "JPA")
    .setParameter("settingKey", "level")
    .setParameter("settingValue", "advanced")
    .setParameter("done", PlanTask.Status.DONE)
    .getResultList();
```

Cách đọc truy vấn:

1. `JOIN p.settings s` tạo bí danh để kiểm tra một cặp key/value.
2. `SIZE(p.tasks) >= :minimumTasks` lọc theo tổng số task.
3. `:requiredSkill MEMBER OF p.skills` kiểm tra membership trong Set giá trị.
4. `NOT EXISTS` loại các plan có task DONE.
5. `DISTINCT p` thể hiện ý định lấy mỗi plan một lần nếu có join sinh nhiều hàng.

**Không buộc phải viết tất cả thành JOIN**. Dùng kết hợp SIZE, MEMBER OF, KEY/VALUE và EXISTS thường phản ánh rõ hơn từng điều kiện nghiệp vụ.

## 23. Lỗi cú pháp thường gặp

### Lỗi 1 — Gọi Java method trong JPQL

```jpql
-- Sai:
WHERE p.tasks.size() >= 3
```

Dùng:

```jpql
WHERE SIZE(p.tasks) >= 3
```

### Lỗi 2 — Dùng SIZE để lấy vị trí

```jpql
-- Sai ý tưởng: SIZE là số lượng, không phải index của task.
WHERE SIZE(t) = 0
```

Dùng `INDEX(t)` trên alias của phần tử được join từ ordered List.

### Lỗi 3 — Dùng INDEX trên cả collection path

```jpql
-- Sai:
WHERE INDEX(p.tasks) = 2
```

Dùng:

```jpql
JOIN p.tasks t
WHERE INDEX(t) = 2
```

### Lỗi 4 — Dùng INDEX trên Set

```jpql
-- Sai về kiểu collection:
SELECT INDEX(s)
FROM LearningPlan p JOIN p.skills s
```

`skills` là Set, không có vị trí 0-based được lưu bằng `@OrderColumn`.

### Lỗi 5 — Dùng @OrderBy rồi nghĩ INDEX chắc chắn hoạt động

`@OrderBy("title ASC")` sắp xếp theo field. `INDEX` yêu cầu ordered List position có mapping phù hợp, điển hình `@OrderColumn`.

### Lỗi 6 — Dùng MEMBER OF trên thuộc tính không phải collection

```jpql
-- name là String basic, không phải collection:
WHERE :name MEMBER OF p.name
```

`MEMBER OF` phải áp lên collection-valued path.

### Lỗi 7 — Dùng MEMBER OF để kiểm tra Map key

Với Map, dùng `JOIN p.settings s WHERE KEY(s) = :key`; không coi `MEMBER OF` là phép kiểm tra key-value bất kỳ của Map.

### Lỗi 8 — Dùng INDEX thay cho KEY của Map

`KEY(s)` dành cho Map key. `INDEX(s)` dành cho vị trí List element.

### Lỗi 9 — Dùng p.tasks.status

`p.tasks` là collection; không đi tiếp tới field của một task tùy ý. Dùng `JOIN p.tasks t WHERE t.status = :status` hoặc EXISTS.

### Lỗi 10 — Dùng SIZE để đếm chỉ những task DONE

`SIZE(p.tasks)` đếm tất cả task; nó không nhận điều kiện `status = DONE`. Dùng COUNT với join/subquery hoặc EXISTS theo nghiệp vụ.

### Lỗi 11 — INNER JOIN rồi nghĩ parent rỗng vẫn có trong thống kê

`JOIN p.tasks t` loại plan không có task. Muốn trả cả 0, dùng `LEFT JOIN` cùng `COUNT(t)` hoặc trực tiếp `SIZE(p.tasks)`.

### Lỗi 12 — LEFT JOIN + WHERE vô tình biến thống kê thành chỉ đếm parent có con

`LEFT JOIN p.tasks t WHERE t.status = :done` loại plan không có task DONE. Nếu cần giữ plan count 0, chuyển điều kiện status vào `ON`.

### Lỗi 13 — JOIN hai collection rồi COUNT bị nhân

Một plan có 3 tasks và 2 skills tạo tối đa 6 hàng join tương ứng. Nếu `COUNT(t)` mà không tính DISTINCT hay thiết kế lại query, kết quả có thể sai.

### Lỗi 14 — Coi INDEX là ID bất biến

Reorder List đổi index nhưng không đổi `@Id`. Không dùng index làm foreign key hoặc ID ổn định để truy cập tài nguyên.

### Lỗi 15 — Nghĩ SIZE không bao giờ tạo SQL nặng

Provider có thể cần đếm hàng liên quan, correlated subquery hoặc aggregate. Với dữ liệu lớn phải xem index và execution plan.

### Lỗi 16 — Nghĩ SIZE luôn phản ánh thay đổi detached chưa merge

JPQL hỏi persistent state/transaction hiện tại. Detached collection đã sửa trong Java không tự đồng bộ với DB; cần workflow merge/update và transaction phù hợp.

### Lỗi 17 — Coi fetch join là cách đếm collection

`JOIN FETCH` có mục tiêu tải entity liên quan, không phải phép count nhẹ. Dùng `SIZE` hoặc aggregate khi chỉ cần số lượng.

### Lỗi 18 — Bỏ qua null parameter

`MEMBER OF` và so sánh trên Map value có logic null/unknown. Validate input hoặc dùng `IS NULL` khi null có ý nghĩa nghiệp vụ.

### Lỗi 19 — Dùng SQL table/column trong JPQL

`SIZE(plan_tasks)` không đúng nếu `plan_tasks` là tên bảng. JPQL dùng `SIZE(p.tasks)` theo thuộc tính Java đã ánh xạ.

### Lỗi 20 — Đoán SQL của provider từ một biểu thức JPQL

Một truy vấn `SIZE` có thể được triển khai bằng nhiều chiến lược SQL. Không hardcode assumptions về số query hay phương án index nếu chưa quan sát trên provider thực tế.

## 24. Bảng lựa chọn theo câu hỏi nghiệp vụ

| Nhu cầu | Biểu thức JPQL nên cân nhắc | Lưu ý |
| --- | --- | --- |
| Plan có ít nhất N tasks | `SIZE(p.tasks) >= :n` | Đếm toàn bộ collection. |
| Plan không có tasks | `p.tasks IS EMPTY` | Diễn đạt trực tiếp rỗng. |
| Plan có ít nhất một task | `p.tasks IS NOT EMPTY` | Không cần biết chính xác count. |
| Plan chứa skill cụ thể | `:skill MEMBER OF p.skills` | Basic value membership. |
| Plan không chứa skill | `:skill NOT MEMBER OF p.skills` | Validate null nếu cần. |
| Plan chứa task entity cụ thể | `:task MEMBER OF p.tasks` | Tham số entity có identity hợp lệ. |
| Task ở index 2 | `JOIN p.tasks t WHERE INDEX(t) = 2` | Cần ordered List mapping. |
| Lấy index và title của task | `SELECT INDEX(t), t.title` | Index 0-based. |
| Lọc Map bằng key | `JOIN p.settings s WHERE KEY(s) = :key` | Không dùng INDEX. |
| Lọc Map bằng key + value | `KEY(s) = :k AND VALUE(s) = :v` | Dùng một alias entry. |
| Truy vấn tất cả Map entries | `SELECT ENTRY(s)` hoặc KEY/VALUE | Chọn projection phù hợp. |
| Đếm task DONE | `LEFT JOIN ... ON ... COUNT(t)` | SIZE không nhận predicate theo status. |
| Tìm plan có task DONE | `EXISTS(...)` hoặc JOIN DISTINCT | Hỏi tồn tại, không cần count. |
| Tìm plan không có task DONE | `NOT EXISTS(...)` | Khác với IS EMPTY. |
| Đếm tasks của mọi plan kể cả 0 | `SIZE(p.tasks)` hoặc LEFT JOIN COUNT | Xét GROUP BY khi aggregate. |
| Tải toàn bộ task cùng plan | `JOIN FETCH` có kiểm soát | Không dùng khi chỉ cần count. |
| Phân trang các task có thứ tự | `SELECT t ... ORDER BY INDEX(t)` | Không phân trang root qua fetch join collection. |

## 25. Tình huống thực hành

### Bài 1 — Kế hoạch có từ 3 nhiệm vụ

Viết JPQL tìm LearningPlan có ít nhất 3 task.

**Đáp án:**

```jpql
SELECT p
FROM LearningPlan p
WHERE SIZE(p.tasks) >= 3
```

Theo dữ liệu mẫu: #10 và #40.

### Bài 2 — Kế hoạch trống

Tìm plan chưa có task.

**Đáp án:**

```jpql
SELECT p
FROM LearningPlan p
WHERE p.tasks IS EMPTY
```

Có thể dùng `SIZE(p.tasks) = 0` nếu muốn biểu diễn cùng điều kiện bằng số lượng.

### Bài 3 — Task ở vị trí thứ hai

Plan #10 có task index 0,1,2. Tìm task ở vị trí thứ hai theo cách đánh số cho người dùng.

**Đáp án:**

```jpql
SELECT t
FROM LearningPlan p JOIN p.tasks t
WHERE p.id = 10
  AND INDEX(t) = 1
```

Kết quả: Task#102 JPQL. Vị trí thứ hai đối với người dùng là **index 1**, không phải 2.

### Bài 4 — Plan chứa kỹ năng Java

```jpql
SELECT p
FROM LearningPlan p
WHERE :skill MEMBER OF p.skills
```

Với `:skill = "Java"`: #10 và #20.

### Bài 5 — Plan có level advanced

```jpql
SELECT DISTINCT p
FROM LearningPlan p
JOIN p.settings s
WHERE KEY(s) = 'level'
  AND VALUE(s) = 'advanced'
```

Kết quả: #10 và #40.

### Bài 6 — Đếm nhiệm vụ của mỗi plan

```jpql
SELECT p.id, SIZE(p.tasks)
FROM LearningPlan p
ORDER BY p.id
```

Kết quả: (10,3), (20,2), (30,0), (40,4).

### Bài 7 — Vì sao COUNT(t) sai khi join cả skills?

```jpql
SELECT p.id, COUNT(t)
FROM LearningPlan p
JOIN p.tasks t
JOIN p.skills s
GROUP BY p.id
```

**Giải thích:** Một task lặp lại trên mỗi skill của cùng plan; `COUNT(t)` đếm số hàng join thay vì số task duy nhất. Dùng `COUNT(DISTINCT t)` hoặc query khác phù hợp; chú ý những plan không có skills sẽ bị loại bởi INNER JOIN.

### Bài 8 — Plan không có task DONE

```jpql
SELECT p
FROM LearningPlan p
WHERE NOT EXISTS (
    SELECT t.id
    FROM PlanTask t
    WHERE t.plan = p
      AND t.status = :done
)
```

Đây là câu hỏi về **trạng thái của phần tử**, không thể thay bằng `SIZE(p.tasks) = 0`.

### Bài 9 — In mọi task theo thứ tự

```jpql
SELECT INDEX(t), t.title
FROM LearningPlan p
JOIN p.tasks t
WHERE p.id = :planId
ORDER BY INDEX(t)
```

Với plan #10: (0, Mapping), (1, JPQL), (2, Transactions).

### Bài 10 — Dời task cuối lên đầu

Java:

```java
LearningPlan plan = em.find(LearningPlan.class, 10L);
PlanTask last = plan.getTasks().remove(2);
plan.getTasks().add(0, last);
```

**Câu hỏi:** Sau flush hợp lệ, `INDEX(t)` của task cuối cũ là bao nhiêu?

**Giải thích:** Task đó chuyển từ index 2 sang index 0. `@Id` của task không đổi.

### Bài 11 — Kiểm tra một entry Map có value null

```jpql
SELECT p
FROM LearningPlan p
JOIN p.settings s
WHERE KEY(s) = :key
  AND VALUE(s) IS NULL
```

**Giải thích:** Query tìm một entry thực sự có key khớp và value null, khác với plan hoàn toàn không có key.

### Bài 12 — Chọn phép kiểm tra hiệu quả hơn

Nghiệp vụ chỉ muốn biết plan có ít nhất một task hay không.

**Gợi ý:** `p.tasks IS NOT EMPTY` diễn đạt rõ hơn điều kiện đếm chính xác. Cũng có thể dùng `SIZE(p.tasks) > 0`; đo query plan nếu hiệu năng là vấn đề quan trọng.

## 26. Câu hỏi tự kiểm tra

**1. `SIZE(p.tasks)` và `plan.getTasks().size()` có phải cùng một thao tác không?**

Không. Một cái là biểu thức JPQL được provider xử lý qua persistent state/database; cái kia là lời gọi Java trên collection, có thể kích hoạt lazy loading và có thể thấy những thay đổi in-memory chưa đồng bộ.

**2. `SIZE` trả gì nếu collection rỗng?**

Trả 0.

**3. Muốn tìm plan có collection rỗng, biểu thức nào rõ nhất?**

`p.tasks IS EMPTY`.

**4. `INDEX(t)` áp lên collection `p.tasks` hay bí danh `t`?**

Áp lên alias của **phần tử List** được tạo bởi `JOIN p.tasks t`.

**5. Index của phần tử đầu tiên là bao nhiêu?**

0.

**6. Khi nào có thể dùng `INDEX` theo ngữ nghĩa portable?**

Khi collection là ordered List có thứ tự được lưu phù hợp, thường qua `@OrderColumn`; không dùng cho Set hoặc Map.

**7. `@OrderBy` có thay thế `@OrderColumn` để tạo vị trí truy vấn bằng INDEX không?**

Không. `@OrderBy` mô tả thứ tự theo thuộc tính, còn `@OrderColumn` lưu vị trí List.

**8. `MEMBER OF` khác `SIZE` thế nào?**

MEMBER OF kiểm tra **một phần tử cụ thể** có thuộc collection hay không; SIZE đếm **tổng số phần tử**.

**9. Tìm Plan có skill JPA bằng biểu thức gì?**

`:skill MEMBER OF p.skills`.

**10. Muốn kiểm tra key của Map, dùng `INDEX` hay `KEY`?**

Dùng `KEY(mapAlias)` sau khi join Map.

**11. Muốn lấy value của entry Map dùng gì?**

`VALUE(mapAlias)`.

**12. Có thể dùng `SIZE(p.tasks)` để đếm riêng task DONE không?**

Không trực tiếp; cần COUNT/EXISTS/JOIN hoặc subquery có điều kiện trên status.

**13. Vì sao cần LEFT JOIN khi đếm child theo từng parent và giữ parent có 0 child?**

INNER JOIN loại parent không có con; LEFT JOIN giữ parent và `COUNT(childAlias)` trả 0 cho hàng không khớp.

**14. Vì sao COUNT sai khi join đồng thời tasks và skills?**

Vì các tập hợp có thể tạo tích số hàng join, khiến một task được đếm nhiều lần.

**15. Có cần fetch toàn bộ collection để dùng SIZE trong JPQL không?**

Không phải mục đích của SIZE; nó có thể được xử lý ở database mà không khởi tạo từng entity con trong Java.

**16. Nếu reorder List, `INDEX(t)` và `Task.id` thay đổi ra sao?**

INDEX thay đổi theo vị trí; entity ID vẫn là danh tính bền vững.

**17. Truy vấn tìm plan không có task DONE nên dùng `IS EMPTY` không?**

Không nếu plan có thể chứa task TODO. `NOT EXISTS` với điều kiện DONE chính xác hơn.

**18. `ENTRY(s)` có ý nghĩa gì?**

Lấy entry key/value của Map trong projection được hỗ trợ, khác với `KEY(s)` hoặc `VALUE(s)` riêng lẻ.

**19. Vì sao tham số null cần được xử lý rõ khi dùng MEMBER OF?**

Do ngữ nghĩa null/unknown có thể không phù hợp với ý định tìm kiếm thông thường; nên validate hoặc xác định quy tắc riêng.

**20. Tại sao không nên lưu index List làm ID cho một task?**

Vì index có thể đổi khi thêm/xóa/reorder; `@Id` của entity là danh tính độc lập.

## 27. Tổng kết

**`SIZE`, `INDEX`, `IS EMPTY`, `MEMBER OF` và các biểu thức Map giúp JPQL đặt câu hỏi trực tiếp về persistent collections**, không cần tải mọi phần tử về Java để lọc/đếm/kiểm tra.

Ghi nhớ các vai trò khác nhau:

- **`SIZE(p.tasks)`:** số phần tử của collection, có thể dùng trong `SELECT` và điều kiện so sánh.
- **`p.tasks IS EMPTY / IS NOT EMPTY`:** kiểm tra collection rỗng hoặc có phần tử.
- **`:x MEMBER OF p.skills`:** kiểm tra giá trị/entity cụ thể thuộc collection.
- **`INDEX(t)`:** vị trí **0-based** của phần tử `t` sau khi join từ **List có `@OrderColumn`**; vị trí có thể thay đổi và không phải entity ID.
- **`KEY(s)`, `VALUE(s)`, `ENTRY(s)`:** truy cập khóa/giá trị/entry của Map đã join.
- **`JOIN + COUNT/EXISTS/GROUP BY`:** công cụ bổ sung khi cần lọc theo điều kiện của từng phần tử hoặc tính aggregate phức tạp.

Không nhầm **`SIZE` với method Java `size()`**, **`INDEX` với `@Id`**, **`@OrderBy` với `@OrderColumn`**, hoặc **`JOIN FETCH` với phép đếm collection**. Khi có nhiều collection joins, luôn xét nguy cơ **nhân số hàng**, sai COUNT, N+1 và chi phí truy vấn.

Một cách thiết kế truy vấn tốt là bắt đầu từ câu hỏi nghiệp vụ: **đếm tất cả, kiểm tra rỗng, kiểm tra phần tử, chọn vị trí, truy cập Map key hay lọc theo điều kiện của child?** Mỗi câu hỏi có một nhóm biểu thức JPQL phù hợp. Khi mô hình collection, transaction và fetch plan được thiết kế rõ, các biểu thức này sẽ giúp truy vấn dữ liệu quan hệ vừa chính xác vừa dễ bảo trì.
