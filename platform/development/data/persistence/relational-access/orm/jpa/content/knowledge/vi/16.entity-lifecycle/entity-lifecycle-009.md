# Xử lý entity đã xóa hoặc entity không còn tồn tại trong cơ sở dữ liệu

Trong **Jakarta Persistence (JPA)**, một đối tượng Java được đánh dấu `@Entity` có thể trải qua nhiều trạng thái: mới tạo (*new*), đang được quản lý (*managed*), đã tách khỏi persistence context (*detached*) và được đánh dấu xóa (*removed*). Khi một entity bị xóa hoặc hàng tương ứng không còn tồn tại trong database, cách ứng dụng xử lý phải phụ thuộc vào **trạng thái JPA của object**, **trạng thái thật của hàng trong database**, và **thời điểm transaction được flush/commit**.

Hai tình huống tưởng giống nhau nhưng rất khác:

1. **Ứng dụng chủ động gọi `entityManager.remove(entity)`:** entity được đánh dấu `removed` trong persistence context; SQL `DELETE` có thể chỉ được thực hiện sau đó, khi flush hoặc commit.
2. **Một hàng đã biến mất khỏi database:** có thể do transaction khác, thao tác bulk/native SQL, cascade ở database, tác vụ quản trị hoặc đơn giản là ID được yêu cầu không tồn tại. Một Java object cũ vẫn có thể nằm trong bộ nhớ, nhưng nó không bảo đảm hàng đó còn tồn tại.

Nếu xử lý không đúng, ứng dụng có thể trả dữ liệu đã xóa, xóa nhầm entity liên quan, hiểu sai `getReference()`, gặp lỗi optimistic locking hoặc trả lời API không nhất quán.

Bài này hướng dẫn cách nhận diện từng tình huống, dùng đúng các API JPA, xử lý transaction và lỗi, phân biệt xóa mềm/xóa vật lý, và thiết kế hành vi phù hợp cho tầng service và HTTP API.

## 1. Hai khái niệm cần tách biệt: object state và database row

Giả sử ứng dụng quản lý công việc có bảng `tasks`:

| id | title | status | version |
| ---: | --- | --- | ---: |
| 101 | Viết tài liệu | OPEN | 0 |
| 102 | Rà soát code | DONE | 2 |

Khi `EntityManager` tải hàng 101, ứng dụng có thể có object:

```java
Task task = entityManager.find(Task.class, 101L);
```

Ở thời điểm này có hai thứ liên quan nhưng không đồng nhất:

- **Object Java `task`:** một instance có thuộc tính `id`, `title`, `status`... được persistence context theo dõi.
- **Hàng database `tasks.id = 101`:** bản ghi tồn tại trong database và chịu các ràng buộc, transaction isolation, locking.

Hình dung:

```text
                    Persistence Context
                  +----------------------+
                  | Task object #101     |
                  | state: MANAGED       |
                  | title: Viết tài liệu |
                  +----------------------+
                             |
                             | ánh xạ theo @Id
                             v
                         Database
                  +----------------------+
                  | tasks.id = 101       |
                  | title = Viết tài liệu|
                  +----------------------+
```

Sau `entityManager.remove(task)`, object Java **không biến mất khỏi bộ nhớ**, nhưng bị đánh dấu xóa theo vòng đời JPA. Sau một thao tác `DELETE` từ transaction khác, hàng database có thể biến mất **mà object Java trong context hiện tại chưa tự biết**.

Vì thế, kiểm tra `task != null` chỉ trả lời rằng biến Java đang giữ một object, **không chứng minh** hàng database còn tồn tại ở thời điểm hiện tại.

## 2. Bốn trạng thái entity và ý nghĩa khi xóa

JPA quy định các trạng thái vòng đời cơ bản:

| Trạng thái | Cách phát sinh điển hình | JPA quản lý thay đổi? | Ý nghĩa đối với xóa |
| --- | --- | --- | --- |
| **New/transient** | `new Task(...)` | Chưa | Chưa có hàng được lưu bởi JPA; xóa database không phải thao tác cần làm cho object mới. |
| **Managed** | `find()`, truy vấn JPA, `persist()` thành công theo vòng đời | Có | Có thể gọi `remove()` để yêu cầu xóa. |
| **Removed** | Gọi `remove()` trên entity managed | Đang được xử lý theo vòng đời xóa | Provider sẽ xóa hàng tương ứng khi đồng bộ; không được tiếp tục dùng như managed entity thông thường. |
| **Detached** | `detach()`, `clear()`, đóng EntityManager | Không | `remove()` trực tiếp không chấp nhận detached entity theo hợp đồng JPA. |

Luồng khái quát:

```text
  new Task(...)
       |
       | persist()
       v
    MANAGED ------ remove() ------> REMOVED
       |
       | detach(), clear(), close()
       v
    DETACHED
       |
       | merge() -> trả về bản managed
       v
    MANAGED (instance trả về)
```

Sơ đồ chỉ thể hiện các chuyển trạng thái thường gặp. Một số chuyển tiếp đặc biệt phụ thuộc thao tác và quy định JPA; không nên suy luận rằng mọi phương thức đều hợp lệ trên mọi trạng thái.

**Removed là trạng thái của entity trong persistence context, không đồng nghĩa hàng đã bị DELETE ngay lập tức.**

### 2.1. Entity mới chưa được lưu

```java
Task task = new Task("Viết tài liệu");
```

Object tồn tại trong bộ nhớ nhưng chưa có bản ghi. Không có ý nghĩa phải tìm một hàng database để xóa nếu chưa từng persist nó.

### 2.2. Entity managed đang tồn tại

```java
Task task = em.find(Task.class, 101L);

if (task != null) {
    em.remove(task);
}
```

Đây là quy trình cơ bản: tải bản managed, rồi yêu cầu xóa. Việc xóa được đồng bộ theo transaction.

### 2.3. Entity đã bị đánh dấu removed

```java
Task task = em.find(Task.class, 101L);
em.remove(task);

// Không tiếp tục sửa task như một entity bình thường.
```

Phương thức `remove()` không giải phóng bộ nhớ Java, cũng không có nghĩa mọi association đã được tải sẽ tự động biến mất khỏi các object khác trong bộ nhớ. Ứng dụng cần xem object đó **không còn là bản ghi đang hoạt động** trong luồng nghiệp vụ.

### 2.4. Entity detached

```java
Task detachedTask = /* nhận từ context cũ */;

// Trong EntityManager mới:
em.remove(detachedTask); // Không phải cách dùng hợp lệ.
```

`remove()` yêu cầu một entity managed. Với detached entity, JPA có thể ném `IllegalArgumentException`. Cách thường an toàn là lấy lại bản managed theo ID trong transaction mới trước khi xóa.

## 3. Entity mẫu để minh họa

Dùng một entity `Task` có khóa sinh tự động và version để biểu diễn đồng thời tình huống xóa thông thường và xung đột cập nhật.

```java
package com.example.tasks;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

@Entity
@Table(name = "tasks")
public class Task {
    public enum Status {
        OPEN, DONE
    }

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 200)
    private String title;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private Status status = Status.OPEN;

    @Version
    @Column(nullable = false)
    private Long version;

    protected Task() {
        // Constructor dành cho JPA.
    }

    public Task(String title) {
        this.title = title;
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public Status getStatus() {
        return status;
    }

    public Long getVersion() {
        return version;
    }

    public void markDone() {
        this.status = Status.DONE;
    }

    public void rename(String newTitle) {
        this.title = newTitle;
    }
}
```

Schema PostgreSQL minh họa:

```sql
CREATE TABLE tasks (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    status VARCHAR(20) NOT NULL,
    version BIGINT NOT NULL,
    CONSTRAINT ck_tasks_status
        CHECK (status IN ('OPEN', 'DONE'))
);
```

`@Version` là metadata phục vụ optimistic locking. Nó không nhất thiết làm mọi tình huống “không tìm thấy” tự biến thành `OptimisticLockException`, nhưng rất hữu ích khi phát hiện một hàng đã bị cập nhật/xóa trong lúc transaction khác đang làm việc.

## 4. Xóa một entity đang tồn tại bằng remove()

Đường đi phổ biến nhất:

```java
Task task = em.find(Task.class, taskId);

if (task != null) {
    em.remove(task);
}
```

### 4.1. find() trả về null khi không có hàng tương ứng

Với một ID không tồn tại và không có managed state/caching làm thay đổi ngữ cảnh:

```java
Task task = em.find(Task.class, 999_999L);

if (task == null) {
    System.out.println("Không tìm thấy Task");
}
```

`EntityManager.find()` là API phù hợp khi muốn **biết entity có được tìm thấy không** và xử lý kết quả `null`.

Một ứng dụng không nên làm:

```java
Task task = em.find(Task.class, taskId);
em.remove(task); // Có thể nhận null khi không tìm thấy.
```

Hãy kiểm tra `null` trước. Nếu `taskId` đến từ HTTP request, cũng cần kiểm tra giá trị ID hợp lệ.

### 4.2. remove() đánh dấu xóa; SQL thực thi khi đồng bộ

```java
Task task = em.find(Task.class, 101L);
em.remove(task);

// Lúc này task ở trạng thái removed trong context.
// SQL DELETE có thể được thực thi khi flush hoặc commit.
```

Một câu SQL xóa ví dụ:

```sql
DELETE FROM tasks
WHERE id = ?
  AND version = ?;
```

Với `@Version`, provider thường kết hợp điều kiện version để phát hiện xung đột. Cú pháp SQL, thứ tự câu lệnh và thời điểm thực thi phụ thuộc provider và flush mode.

**Không coi việc `remove()` trả về bình thường là bằng chứng transaction đã commit và hàng đã bị xóa bền vững.** Một lỗi constraint hoặc optimistic locking có thể chỉ xuất hiện khi flush/commit; transaction cũng có thể rollback.

### 4.3. Xóa entity khác với đặt biến Java về null

```java
Task task = em.find(Task.class, 101L);
task = null;
```

Đoạn code chỉ đổi tham chiếu của biến local. Nó **không gửi yêu cầu xóa hàng** đến JPA và không tương đương `em.remove()`.

Ngược lại:

```java
Task task = em.find(Task.class, 101L);
em.remove(task);

System.out.println(task.getId()); // Object Java có thể vẫn còn giá trị ID.
```

Object không biến mất khỏi heap khi yêu cầu xóa. Nhưng không nên dùng object đang removed để làm dữ liệu nghiệp vụ còn tồn tại, hoặc coi field cũ của nó là giá trị database hiện tại.

## 5. Ví dụ xóa an toàn trong một transaction Java SE

Giả sử persistence unit cấu hình `RESOURCE_LOCAL` và `EntityManagerFactory` đã tồn tại.

```java
package com.example.tasks;

import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.EntityTransaction;

public final class TaskDeletionService {
    private final EntityManagerFactory factory;

    public TaskDeletionService(EntityManagerFactory factory) {
        this.factory = factory;
    }

    /**
     * @return true nếu tìm thấy Task để yêu cầu xóa;
     *         false nếu không tìm thấy.
     */
    public boolean deleteById(long taskId) {
        EntityManager em = factory.createEntityManager();

        try {
            EntityTransaction tx = em.getTransaction();

            try {
                tx.begin();

                Task task = em.find(Task.class, taskId);
                if (task == null) {
                    tx.commit();
                    return false;
                }

                em.remove(task);
                tx.commit(); // Có thể phát sinh SQL/constraint/locking ở đây.
                return true;
            } catch (RuntimeException ex) {
                if (tx.isActive()) {
                    tx.rollback();
                }
                throw ex;
            }
        } finally {
            em.close();
        }
    }
}
```

Đoạn code minh họa các điểm nền tảng:

1. **Tạo EntityManager cho đơn vị công việc**; không chia sẻ cùng một instance cho nhiều thread.
2. **Bắt đầu transaction** trước thao tác xóa cần được cam kết.
3. **Tải entity managed** và kiểm tra không tồn tại.
4. **Gọi remove** đúng một entity theo yêu cầu.
5. **Commit** để hoàn tất transaction; xử lý lỗi xảy ra muộn tại commit.
6. **Rollback khi còn transaction hoạt động**, sau đó đóng EntityManager.

Kết quả `true` chỉ được trả về sau khi `commit()` không ném lỗi. Nếu delete thất bại do constraint, ví dụ không trả `true` một cách giả tạo.

Trong Jakarta EE dùng JTA hoặc Spring sử dụng `@Transactional`, transaction có thể do framework quản lý; không sao chép phần `getTransaction().begin()/commit()` sang `EntityManager` được container quản lý.

## 6. remove() trên new, removed và detached entity

`EntityManager.remove()` không có cùng ý nghĩa với mọi trạng thái.

| Trạng thái trước thao tác | Hành vi cần hiểu |
| --- | --- |
| **Managed** | Entity được đánh dấu removed; việc xóa được xử lý khi đồng bộ transaction. |
| **Removed** | Yêu cầu remove lặp trên chính entity đã removed thường được bỏ qua theo hợp đồng lifecycle. |
| **New** | Một entity mới chưa persistent không có hàng để xóa; JPA có quy tắc bỏ qua remove đối với chính new entity, nhưng cascade REMOVE có thể được áp dụng lên các association phù hợp. |
| **Detached** | Không được remove như managed entity; thường báo `IllegalArgumentException`. |

Với entity mới:

```java
Task newTask = new Task("Chưa lưu");
em.remove(newTask);

// Không phải thao tác DELETE một hàng vì Task này chưa được persist.
```

Đây không phải lý do để gọi `remove()` trên mọi object tùy ý. Ngay cả khi remove trên new entity không xóa hàng của nó, các cascade relation có thể có tác động khác, nên ứng dụng cần giữ ranh giới nghiệp vụ rõ ràng.

Với detached:

```java
Task detached = /* entity đã tải từ EntityManager khác */;

// Không nên:
em.remove(detached);
```

Thay bằng:

```java
Task managed = em.find(Task.class, detached.getId());

if (managed != null) {
    em.remove(managed);
}
```

Cách này tránh phụ thuộc vào trạng thái cũ của detached instance và cho phép xem dữ liệu hiện tại của hàng trước khi quyết định xóa.

### 6.1. Có nên merge(detached) rồi remove?

Một mẫu đôi khi được viết:

```java
Task managed = em.merge(detached);
em.remove(managed);
```

Về mặt API, `merge()` trả về một instance managed để tiếp tục thao tác. Nhưng với nghiệp vụ **chỉ cần xóa theo ID**, merge có thể không phải lựa chọn tốt:

- Detached object có thể chứa dữ liệu cũ hoặc không đáng tin.
- `merge()` có thể sao chép state của object cũ vào bản managed.
- Cascade MERGE có thể kéo theo các entity liên quan.
- Nếu hàng đã biến mất, hành vi merge có thể không phù hợp với giả định “chỉ xóa nếu còn tồn tại”.

Thông thường **find → kiểm tra quyền, điều kiện nghiệp vụ → remove** dễ kiểm soát hơn. Không dùng `merge` chỉ như một bước “ép entity trở thành managed” mà không cân nhắc tác động.

## 7. Entity đã removed nhưng hàng chưa bị xóa vật lý

Một tình huống cần phân biệt rõ:

```java
Task task = em.find(Task.class, 101L);
em.remove(task);

// Chưa gọi flush/commit.
```

Ở thời điểm này, hàng `tasks.id = 101` **có thể vẫn hiện diện trong database** vì SQL `DELETE` còn đang chờ flush. Tuy nhiên, persistence context biết entity đã được đánh dấu xóa.

Mô hình thời gian:

```text
T0: find(Task#101)
    Java: MANAGED        DB: row 101 tồn tại

T1: remove(task)
    Java: REMOVED        DB: row 101 có thể vẫn tồn tại

T2: flush()
    Java: REMOVED        DB trong transaction: row 101 bị DELETE

T3: commit()
    Transaction thành công: delete được cam kết bền vững

Hoặc T3: rollback()
    DB quay về trạng thái trước transaction,
    Java objects/context không được coi là tự reset hoàn chỉnh.
```

### 7.1. Không dựa vào SELECT thủ công để phủ nhận trạng thái removed

Nếu chạy một câu SQL trực tiếp trước flush, SQL có thể nhìn thấy hàng mà JPA đã đánh dấu xóa trong bộ nhớ. Điều đó không có nghĩa `remove()` không có tác dụng.

Ngược lại, nếu dùng JPQL query với flush mode `AUTO`, provider có thể flush trước khi chạy query, khiến hàng đã bị xóa trong transaction ngay tại thời điểm truy vấn. Vì vậy, thời điểm thấy hàng trong database phụ thuộc **flush, transaction và cách truy vấn**, không chỉ số lần gọi remove.

### 7.2. Không dùng find() sau remove() để quyết định lại nghiệp vụ

Một luồng như:

```java
Task task = em.find(Task.class, 101L);
em.remove(task);

Task again = em.find(Task.class, 101L);
```

không nên được dùng như phép thử rằng SQL `DELETE` đã chạy hay chưa. Cùng persistence context có thể chứa thông tin về một entity đang removed, và hành vi quan sát gắn với quy tắc lifecycle, cache và provider.

Muốn xác nhận xóa thành công, hãy dựa vào **kết quả transaction/commit** và kiểm tra trạng thái bằng **đơn vị công việc mới** nếu thật sự cần xác minh. Đừng tự chèn thêm `find()` trong transaction chỉ để “chứng minh đã xóa”.

## 8. Khi entity không còn tồn tại: find() và getReference() khác nhau

JPA có hai API dễ nhầm:

```java
Task task = em.find(Task.class, id);
```

và:

```java
Task taskRef = em.getReference(Task.class, id);
```

**`find()`** được dùng khi cần tải hoặc kiểm tra một entity. Với ID không tồn tại, nó có thể trả `null`.

**`getReference()`** trả về tham chiếu đến entity theo khóa chính mà **không nhất thiết tải ngay toàn bộ state**. Provider có thể tạo proxy/đại diện trì hoãn hoặc cách biểu diễn khác. Từ đó phát sinh một điểm nguy hiểm: **lấy được tham chiếu không chứng minh hàng đang tồn tại**.

### 8.1. Ví dụ getReference() đến ID không có thật

```java
Task ref = em.getReference(Task.class, 999_999L);

// Không được suy luận rằng ID này tồn tại chỉ vì nhận được ref.
String title = ref.getTitle(); // Có thể kích hoạt tải và phát hiện thiếu hàng.
```

Nếu hàng không tồn tại, provider có thể ném `EntityNotFoundException` khi truy cập trạng thái. Một số provider cũng được phép xác minh và ném ngoại lệ sớm hơn, ngay khi gọi `getReference()`.

Cách dùng đúng phụ thuộc mục tiêu:

- **Muốn biết hàng có tồn tại không:** dùng `find()` rồi xử lý `null`.
- **Muốn đặt một association bằng ID đã được xác thực trong một luồng có kiểm soát:** có thể cân nhắc `getReference()` để tránh nạp toàn bộ entity, nhưng không bỏ qua constraint/validation cần thiết.
- **Muốn xử lý lỗi “không tồn tại” theo cách rõ ràng:** `find()` thường dễ đọc và dễ kiểm soát hơn.

### 8.2. getReference() với EntityManager đã đóng

Nếu tham chiếu là một proxy chưa khởi tạo, việc truy cập nó sau khi persistence context đóng có thể gặp lỗi lazy initialization đặc thù provider, chẳng hạn `LazyInitializationException` của Hibernate.

Đó là một vấn đề khác với `EntityNotFoundException`:

- Một lỗi vì **không còn context để tải**.
- Một lỗi vì **hàng được tham chiếu không tồn tại** khi hệ thống cố truy cập.

Không nên gom hai tình huống thành cùng một thông điệp “ID không hợp lệ” nếu nguyên nhân thật là ranh giới transaction/persistence context.

## 9. Truy vấn JPQL khi không có kết quả

Ngoài `find()`, JPA có truy vấn theo điều kiện:

```java
List<Task> tasks = em.createQuery(
        "SELECT t FROM Task t WHERE t.title = :title",
        Task.class
    )
    .setParameter("title", "Không tồn tại")
    .getResultList();
```

Khi không có hàng phù hợp, `getResultList()` trả về **danh sách rỗng**, không phải `null`.

Nếu dùng `getSingleResult()`:

```java
Task task = em.createQuery(
        "SELECT t FROM Task t WHERE t.title = :title",
        Task.class
    )
    .setParameter("title", "Không tồn tại")
    .getSingleResult();
```

truy vấn không có kết quả sẽ ném `NoResultException`, còn nhiều kết quả có thể gây `NonUniqueResultException`. Hai ngoại lệ này **không có nghĩa entity đang removed**; chúng chỉ cho biết kết quả truy vấn không đáp ứng yêu cầu “đúng một hàng”.

Trong các phiên bản JPA hỗ trợ stream:

```java
Task task = em.createQuery(
        "SELECT t FROM Task t WHERE t.title = :title",
        Task.class
    )
    .setParameter("title", "Không tồn tại")
    .getResultStream()
    .findFirst()
    .orElse(null);
```

Nhưng nếu cần một bản ghi duy nhất theo nghiệp vụ, vẫn nên có **unique constraint** ở database và không dùng `findFirst()` để che dữ liệu trùng ngoài dự kiến.

## 10. Một transaction khác đã xóa hàng: managed entity có thể bị lỗi thời

Giả sử hai giao dịch hoạt động độc lập:

```text
Transaction A                       Transaction B
-------------                       -------------
find Task#101
Task#101 đang MANAGED

                                    find Task#101
                                    remove(Task#101)
                                    commit thành công

A vẫn giữ object Task#101
A gọi task.getTitle()
=> Có thể đọc giá trị trong bộ nhớ.

A cố update/remove Task#101
=> Có thể gặp lỗi khi flush/commit,
   phụ thuộc @Version/provider/isolation.
```

**JPA không tự phát thông báo đến mọi persistence context khác mỗi khi một hàng bị xóa.** Managed object trong transaction A vẫn có các field Java của nó, dù database đã mất hàng sau commit của B.

Đây là **stale persistence context**, không phải JPA đã tạo lại hàng.

### 10.1. Đọc field của object cũ không phải phép kiểm tra tồn tại

```java
Task task = emA.find(Task.class, 101L);

// B xóa và commit Task#101.

System.out.println(task.getTitle());
```

Nếu `title` đã được tải, getter có thể trả giá trị cũ từ bộ nhớ. Không nên kết luận database còn hàng dựa trên getter này.

### 10.2. Refresh khi hàng đã bị xóa

Một cách yêu cầu database đọc lại state của managed entity là:

```java
emA.refresh(task);
```

Nếu hàng không còn tồn tại và tình trạng xóa đó **nhìn thấy được theo transaction isolation**, refresh có thể ném `EntityNotFoundException` hoặc ngoại lệ theo hợp đồng JPA/provider.

Lưu ý:

- `refresh()` yêu cầu managed entity, không dùng tùy tiện trên detached/removed object.
- Refresh có thể **ghi đè sửa đổi chưa flush** của entity.
- Refresh chịu ảnh hưởng **transaction isolation và locking**; không bảo đảm nhìn thấy mọi commit mới nhất dưới mọi mức cô lập.
- Ngoại lệ refresh có thể làm transaction không còn phù hợp để tiếp tục; cần xử lý rollback và kết thúc đơn vị công việc.

Vì vậy, refresh chỉ nên dùng khi **thực sự muốn đồng bộ managed object với database**, không phải thay thế thiết kế concurrency và transaction.

### 10.3. find() trong context đang giữ object cũ

Nếu cùng persistence context đã có managed `Task#101`, một lần `find(Task.class, 101L)` khác có thể trả lại chính instance cũ. Nó không phải “lệnh kiểm tra tồn tại trực tiếp ở database” mỗi lần.

Muốn có góc nhìn mới sau khi transaction khác commit, có thể thiết kế một **transaction và persistence context mới** hoặc dùng refresh có chủ đích, nhưng vẫn cần xem isolation và cache.

## 11. Optimistic locking khi update hoặc delete hàng đã biến mất

Đối với entity có `@Version`, JPA thường dùng version để phát hiện cập nhật/xóa trên một bản dữ liệu đã bị thay đổi bởi transaction khác.

Giả sử có hàng:

```text
tasks.id = 101
tasks.version = 2
```

Transaction A đã tải phiên bản 2. Transaction B xóa và commit hàng 101. A sau đó cập nhật hoặc xóa bản Task đã tải.

Provider có thể gửi lệnh tương tự:

```sql
UPDATE tasks
SET title = ?, version = 3
WHERE id = 101 AND version = 2;
```

hoặc:

```sql
DELETE FROM tasks
WHERE id = 101 AND version = 2;
```

Nếu hàng đã bị xóa, số hàng bị ảnh hưởng là **0**. Provider có thể phát hiện sự không khớp và ném `OptimisticLockException` hoặc ngoại lệ persistence/transaction tương ứng.

### 11.1. Trường hợp hai transaction cùng xóa

```text
A: Đọc Task#101 (version=2)
B: Đọc Task#101 (version=2)

A: remove(Task#101) -> commit -> thành công
B: remove(Task#101) -> flush/commit -> có thể báo conflict
```

Việc hai request cùng muốn xóa **không nhất thiết đồng nghĩa request thứ hai thành công mà không có lỗi**. Nếu B giữ managed entity phiên bản cũ và cố xóa, optimistic locking có thể phát hiện stale state.

Ngược lại, nếu request B mới bắt đầu **sau khi A đã commit** và gọi `find(101)` trong context mới, B có thể nhận `null` mà không phải tạo một lệnh delete có version.

Hai tình huống cần phân biệt:

- **Không tìm thấy trước khi ra lệnh xóa** → xử lý thiếu tài nguyên theo hợp đồng nghiệp vụ.
- **Đã tìm thấy nhưng mất hoặc thay đổi trong khi đang xóa** → có thể là **concurrency conflict**, cần xử lý transaction/locking.

### 11.2. Không có @Version thì sao?

Một entity không có `@Version` vẫn có thể bị ảnh hưởng bởi xóa đồng thời, ràng buộc khóa ngoại và số hàng SQL bị ảnh hưởng. Hành vi phát hiện stale delete/update có thể phụ thuộc provider, database và phương thức thực thi.

Không nên mặc định rằng thiếu `@Version` thì luôn an toàn, hoặc JPA luôn ném đúng cùng một ngoại lệ cho mọi biến cố xóa đồng thời. Nếu ứng dụng cần xác định rõ **ai đã sửa/xóa trước**, nên thiết kế optimistic locking hoặc cơ chế concurrency phù hợp.

### 11.3. Một ID tồn tại lúc find không bảo đảm còn tồn tại lúc remove

Ngay cả khi:

```java
Task task = em.find(Task.class, id);
if (task != null) {
    em.remove(task);
}
```

transaction khác vẫn có thể xóa hàng **giữa find và thời điểm DELETE thực tế**. Đây là tình huống *time-of-check to time-of-use*. Việc kiểm tra null chỉ chứng minh hàng tồn tại theo góc nhìn lúc đọc, không giữ hàng đó mãi tồn tại.

Nếu cần khóa mạnh hơn trong quá trình kiểm tra/xóa, có thể cân nhắc `LockModeType.PESSIMISTIC_WRITE` trong transaction khi DB/provider hỗ trợ, hoặc dùng câu lệnh DELETE có điều kiện và kiểm tra affected rows. Những lựa chọn này có chi phí khóa và phải tuân thủ quy tắc isolation.

## 12. Bảng quyết định các tình huống “không còn tồn tại”

| Tình huống | Dấu hiệu | Hướng xử lý |
| --- | --- | --- |
| ID chưa từng tồn tại | `find()` trả `null` trong context phù hợp | Trả “không tìm thấy” hoặc coi delete là idempotent no-op theo API. |
| Entity được đánh dấu removed trong transaction này | Code đã gọi `remove()` | Không tiếp tục dùng object như active entity; chờ flush/commit hoặc rollback. |
| Object detached của request cũ | Không managed; `remove(detached)` không hợp lệ | Tải managed entity theo ID trong transaction mới. |
| `getReference()` trỏ đến ID không tồn tại | `EntityNotFoundException` khi lấy/truy cập tham chiếu | Không coi proxy là bằng chứng tồn tại; kiểm tra bằng `find()` nếu cần. |
| Hàng bị transaction khác xóa sau khi ta đã đọc | Managed entity lỗi thời | Xử lý concurrency; refresh/reload có chủ đích, không dùng state cũ làm sự thật. |
| Update/remove gặp 0 affected rows | Có thể phát sinh optimistic/stale state error | Rollback, làm rõ xung đột và quyết định retry hoặc báo caller. |
| JPQL query không có kết quả | Danh sách rỗng hoặc `NoResultException` | Xử lý kết quả truy vấn; không mặc định gọi `remove()`. |
| Hàng bị bulk/native SQL xóa trong chính transaction | Managed instance có thể vẫn còn | Làm sạch context hoặc reload theo thiết kế, lưu ý thay đổi chưa flush. |
| Entity bị “xóa mềm” | Hàng còn nhưng có `deletedAt` hoặc `deleted=true` | Áp dụng chính sách lọc/không truy cập, khác với xóa vật lý. |

Điểm chung là: **không có một exception duy nhất đại diện mọi loại entity đã xóa**. Hành vi phụ thuộc **API đang gọi, trạng thái entity và thời điểm phát hiện thiếu hàng**.

## 13. Cascade REMOVE và khóa ngoại khi xóa entity cha

Giả sử một `Project` chứa nhiều `Task`; mỗi task có khóa ngoại `project_id`.

```text
Project#10
    +-- Task#101
    +-- Task#102

projects.id = 10
tasks.project_id = 10
```

Nếu database có:

```sql
ALTER TABLE tasks
ADD CONSTRAINT fk_tasks_project
FOREIGN KEY (project_id) REFERENCES projects(id);
```

việc xóa Project#10 khi còn Task phụ thuộc có thể bị từ chối bởi constraint khóa ngoại.

### 13.1. Mapping không cascade

Ví dụ:

```java
@Entity
public class Project {
    @Id
    private Long id;

    @OneToMany(mappedBy = "project")
    private List<Task> tasks = new ArrayList<>();
}
```

```java
@Entity
public class Task {
    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "project_id", nullable = false)
    private Project project;
}
```

**Hai đoạn trên là mapping minh họa riêng**; nếu kết hợp vào ứng dụng thực tế, hãy dùng một định nghĩa `Task` thống nhất, không tạo trùng class với entity `Task` ở phần đầu.

Trong mapping không có cascade REMOVE, gọi:

```java
em.remove(project);
```

không tự yêu cầu `remove()` cho mọi Task. Nếu còn hàng tham chiếu bằng FK `NOT NULL` và không có database cascade, flush/commit có thể thất bại vì ràng buộc khóa ngoại.

Hướng xử lý phụ thuộc nghiệp vụ:

1. **Không cho xóa Project nếu còn Task**: trả lỗi nghiệp vụ rõ ràng.
2. **Chuyển Task sang Project khác**: cập nhật owning side `Task.project` và giữ khóa ngoại hợp lệ.
3. **Xóa các Task trước**: nếu vòng đời task thật sự phụ thuộc project.
4. **Chọn soft delete cho Project**: nếu muốn giữ lịch sử.

### 13.2. CascadeType.REMOVE

Với project sở hữu toàn bộ vòng đời các task, có thể khai báo:

```java
@OneToMany(
    mappedBy = "project",
    cascade = CascadeType.REMOVE
)
private List<Task> tasks = new ArrayList<>();
```

Khi `remove(project)`, JPA lan truyền thao tác remove sang các Task trong quan hệ theo quy tắc cascade. Provider sắp xếp SQL phù hợp với FK và transaction.

Nếu ứng dụng cũng tạo Project cùng Task mới qua `persist(project)`, có thể cần thêm `CascadeType.PERSIST`. **Cascade REMOVE không mặc nhiên bao gồm PERSIST**; `CascadeType.ALL` bao gồm mọi loại cascade, cần cân nhắc hậu quả trước khi dùng.

### 13.3. Đừng cascade REMOVE tới entity được chia sẻ

Ví dụ `Task` tham chiếu một `User` là người phụ trách:

```java
@ManyToOne(fetch = FetchType.LAZY)
private User assignee;
```

Nếu xóa Task, thông thường **không được xóa luôn User**. Do đó không nên viết:

```java
@ManyToOne(cascade = CascadeType.REMOVE)
private User assignee;
```

Một `User` có thể liên kết với nhiều Task và có vòng đời độc lập. Cascade REMOVE có thể xóa nhầm dữ liệu hoặc gây lỗi FK.

Cách chọn cascade là quyết định về **quyền sở hữu vòng đời của entity**, không phải chỉ để dọn lỗi constraint.

## 14. orphanRemoval khác với remove() trực tiếp

`orphanRemoval = true` trên quan hệ phù hợp có ý nghĩa **xóa entity con khi nó bị loại khỏi association sở hữu**.

Ví dụ:

```java
@OneToMany(
    mappedBy = "project",
    cascade = {CascadeType.PERSIST, CascadeType.MERGE},
    orphanRemoval = true
)
private List<Task> tasks = new ArrayList<>();
```

Nếu ứng dụng gỡ Task#101 ra khỏi `project.tasks` và cập nhật cả phía sở hữu `task.project` theo quy tắc của mapping, provider có thể xóa Task#101 tại flush.

Cần phân biệt:

| Thao tác | Cơ chế |
| --- | --- |
| `em.remove(task)` | Yêu cầu xóa trực tiếp entity Task đang managed. |
| `em.remove(project)` với cascade REMOVE | Xóa cha và lan truyền remove tới các con liên quan. |
| `project.tasks.remove(task)` khi orphanRemoval=true | Entity con bị loại khỏi quan hệ sở hữu và được xử lý như orphan theo mapping. |
| `project.tasks.remove(task)` khi orphanRemoval=false | Không mặc nhiên tương đương xóa Task; có thể chỉ thay đổi liên kết, hoặc không có tác động SQL nếu chỉ sửa inverse side. |

Nếu Task được phép **chuyển từ Project A sang Project B mà vẫn giữ ID**, đừng mặc định dùng orphanRemoval. Một Task bị gỡ khỏi owner cũ có thể bị đánh dấu xóa; gán lại orphan vào owner mới không phải hành vi được JPA bảo đảm portable.

## 15. Cascade JPA khác với ON DELETE CASCADE của database

Có hai loại “cascade delete” khác tầng:

**JPA cascade:**

```java
@OneToMany(
    mappedBy = "project",
    cascade = CascadeType.REMOVE
)
private List<Task> tasks;
```

**Database cascade:**

```sql
FOREIGN KEY (project_id)
    REFERENCES projects(id)
    ON DELETE CASCADE
```

Khác biệt:

- `CascadeType.REMOVE` là **JPA truyền thao tác vòng đời** tới các entity liên quan. Nó có thể liên quan callback `@PreRemove`, version và trạng thái persistence context theo các quy tắc tương ứng.
- `ON DELETE CASCADE` là **database xóa hàng phụ thuộc** khi SQL xóa hàng cha. Nó không yêu cầu JPA tự gọi remove cho từng entity con.
- Nếu database xóa Task nhờ `ON DELETE CASCADE` nhưng persistence context đang giữ một `Task` managed, object đó **có thể bị lỗi thời**.
- `@PreRemove` của Task không được đảm bảo chạy chỉ vì database tự xóa hàng bằng FK cascade.

Không nên sử dụng đồng thời hai cơ chế mà không hiểu phạm vi, chi phí và hậu quả đối với cache/version. Nếu ứng dụng dùng provider-specific optimization cho database cascade, cần kiểm tra tài liệu và SQL thực tế của provider.

## 16. Xóa bằng JPQL bulk DELETE: nhanh nhưng bỏ qua vòng đời entity

JPA hỗ trợ xóa hàng loạt trực tiếp:

```java
int affected = em.createQuery(
        "DELETE FROM Task t WHERE t.status = :status"
    )
    .setParameter("status", Task.Status.DONE)
    .executeUpdate();
```

Hoặc xóa đúng ID:

```java
int affected = em.createQuery(
        "DELETE FROM Task t WHERE t.id = :id"
    )
    .setParameter("id", taskId)
    .executeUpdate();
```

`executeUpdate()` trả về số entity bị tác động theo kết quả thao tác bulk. Với điều kiện chỉ theo PK của một entity và mapping/schema đơn giản, `affected = 0` thường có nghĩa không có hàng nào được xóa qua câu lệnh đó; `affected = 1` thường là một hàng đã bị tác động.

Tuy nhiên, **bulk DELETE không tương đương gọi `em.remove(task)` trên từng entity**:

1. Bỏ qua cơ chế đồng bộ state của các managed instances đã tải.
2. Không tự cascade REMOVE theo association như thao tác entity thường.
3. Không gọi lifecycle callbacks `@PreRemove`/`@PostRemove` cho từng entity theo cách remove entity.
4. Không tự kiểm tra version của từng entity như một câu remove managed entity có `@Version`.
5. Có thể gặp lỗi khóa ngoại do database nếu còn hàng phụ thuộc.
6. Có thể để lại managed entity lỗi thời trong persistence context hiện tại.

### 16.1. Ví dụ persistence context bị lỗi thời sau bulk delete

```java
Task task = em.find(Task.class, 101L);

int affected = em.createQuery(
        "DELETE FROM Task t WHERE t.id = :id"
    )
    .setParameter("id", 101L)
    .executeUpdate();

// Database có thể đã xóa hàng 101, nhưng object task vẫn nằm trong context.
System.out.println(task.getTitle()); // Có thể đọc giá trị cũ.
```

Nếu muốn tiếp tục đọc dữ liệu sau bulk delete, có thể dùng:

```java
em.clear();

// Task#101 không còn được giữ làm managed instance trong context.
Task reloaded = em.find(Task.class, 101L);
```

Nhưng `clear()` **tách tất cả managed entities**, kể cả những entity có thay đổi chưa flush. Vì vậy, trước khi bulk delete/clear, cần thiết kế rõ:

- Các thay đổi nào phải được flush trước?
- Có managed instance nào đang được code khác giữ và sử dụng không?
- Có cache cấp hai của provider cần xử lý không?
- Có constraint/cascade/callback nào bắt buộc phải chạy không?

Đối với một entity đơn lẻ, `find → remove` thường dễ bảo toàn vòng đời và business rule hơn bulk delete. Bulk delete thích hợp khi có chủ đích thao tác trên nhiều hàng và chấp nhận những giới hạn kể trên.

### 16.2. Bulk delete không thay thế optimistic locking

Một câu:

```java
DELETE FROM Task t WHERE t.id = :id
```

không kiểm tra phiên bản cũ của Task. Nếu cần tránh xóa một hàng đã được người khác cập nhật, có thể thiết kế điều kiện thêm version:

```java
int affected = em.createQuery(
        "DELETE FROM Task t " +
        "WHERE t.id = :id AND t.version = :expectedVersion"
    )
    .setParameter("id", taskId)
    .setParameter("expectedVersion", expectedVersion)
    .executeUpdate();

if (affected == 0) {
    // Có thể không tồn tại hoặc version đã thay đổi.
    // Phải phân biệt theo hợp đồng nghiệp vụ nếu cần.
}
```

Đây là optimistic concurrency được **tự thiết kế trong câu bulk JPQL**; nó không khôi phục đầy đủ callback/cascade và state management của `remove()`. Nếu cần biết rõ hàng đã bị xóa hay chỉ khác version, có thể cần thêm truy vấn hoặc kết quả nghiệp vụ chuyên biệt, đồng thời chấp nhận khả năng dữ liệu thay đổi giữa những lần đọc.

## 17. @PreRemove, @PostRemove và callback khi xóa

JPA hỗ trợ các lifecycle callbacks:

```java
@PreRemove
void beforeRemove() {
    // Ví dụ: logic xử lý trước thao tác remove.
}

@PostRemove
void afterRemove() {
    // Ví dụ: callback sau thao tác remove theo vòng đời JPA.
}
```

Các callback này có thể được khai báo trên entity hoặc trong entity listener, tùy cấu hình. Chúng có ích khi cần điều phối một số logic liên quan đến entity lifecycle.

Nhưng cần cẩn trọng:

- Callback **không phải** tín hiệu rằng transaction đã commit thành công. Transaction vẫn có thể rollback.
- Không nên gửi ngay email/thông báo không thể hoàn tác trong `@PreRemove` hoặc `@PostRemove`.
- Bulk JPQL DELETE, native SQL DELETE hoặc database `ON DELETE CASCADE` **không thực hiện lifecycle callback cho từng entity giống `remove()`**.
- Callback có những hạn chế về truy cập EntityManager, truy vấn và thay đổi association theo quy định JPA/runtime; không nên nhồi toàn bộ logic nghiệp vụ phức tạp vào callback.

Nếu cần công bố sự kiện “Task đã bị xóa” cho hệ thống khác **sau khi commit**, có thể dùng transaction synchronization hoặc **transactional outbox pattern**. Một event phát đi trước commit có thể thông báo sai nếu transaction xóa cuối cùng thất bại.

## 18. Soft delete: entity “đã xóa” nhưng hàng vẫn tồn tại

Không phải mọi hệ thống đều xóa vật lý. Với lịch sử giao dịch, hồ sơ hoặc dữ liệu cần khôi phục, nghiệp vụ có thể dùng **soft delete**:

```sql
ALTER TABLE tasks
ADD COLUMN deleted_at TIMESTAMP NULL;
```

Khi người dùng xóa một Task, thay vì `DELETE`:

```sql
UPDATE tasks
SET deleted_at = CURRENT_TIMESTAMP
WHERE id = ?;
```

Hàng vẫn tồn tại, nhưng ứng dụng xem nó không còn hoạt động.

### 18.1. Mapping soft delete cơ bản

```java
@Column(name = "deleted_at")
private java.time.LocalDateTime deletedAt;

public void markDeleted(java.time.LocalDateTime time) {
    this.deletedAt = time;
}
```

Ví dụ trong một entity có field `deletedAt`:

```java
Task task = em.find(Task.class, id);
if (task != null && task.getDeletedAt() == null) {
    task.markDeleted(java.time.LocalDateTime.now());
}
```

Đây là **một biến thể thiết kế** của entity `Task`; muốn dùng code, phải bổ sung field/getter/method đã minh họa vào lớp thực tế. Không nên đồng thời gọi `em.remove(task)` nếu nghiệp vụ chỉ muốn soft delete.

### 18.2. Soft delete khác với entity state REMOVED

Sau một cập nhật soft delete thông thường:

- Entity vẫn là **managed**, không trở thành `removed`.
- Hàng database vẫn tồn tại.
- `EntityManager.find(Task.class, id)` có thể vẫn trả entity ấy nếu không có cơ chế lọc soft-delete thích hợp.
- Unique constraint, foreign key và lịch sử vẫn áp dụng trên hàng.
- Việc khôi phục có thể chỉ là đặt `deletedAt = null`, nếu domain cho phép.

Vì vậy, **soft-deleted entity là trạng thái nghiệp vụ**, khác với **JPA removed state**. Không nên nhầm `deletedAt != null` với một entity đã bị `EntityManager.remove()`.

### 18.3. Cần chính sách truy vấn nhất quán

Nếu dùng soft delete, truy vấn ứng dụng thường cần điều kiện:

```java
List<Task> activeTasks = em.createQuery(
        "SELECT t FROM Task t " +
        "WHERE t.deletedAt IS NULL",
        Task.class
    )
    .getResultList();
```

Không chỉ truy vấn list, các API như `find`, relation fetching, tính số lượng, unique business rule và quy trình khôi phục cũng cần chính sách xử lý nhất quán.

Một số provider có tính năng lọc/soft delete riêng, nhưng **không nên cho rằng JPA chuẩn tự động ẩn mọi hàng có `deletedAt`**. Khi cần, thiết kế repository/query hoặc sử dụng tính năng provider với hiểu biết rõ về phạm vi áp dụng.

## 19. Xóa một entity đã được tham chiếu từ entity khác

Giả sử một `Task` được `WorkLog` tham chiếu:

```sql
CREATE TABLE work_logs (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    task_id BIGINT NOT NULL REFERENCES tasks(id),
    logged_minutes INTEGER NOT NULL
);
```

Khi xóa Task#101, database có thể từ chối vì còn work log tham chiếu. Đây là **ràng buộc toàn vẹn dữ liệu**, không phải lỗi “Task không tồn tại”.

Các lựa chọn nghiệp vụ:

- **Cấm xóa Task có work log**; báo rõ vì sao và hướng xử lý.
- **Lưu trữ/soft delete Task** để giữ báo cáo và audit.
- **Xóa work log cùng Task** nếu domain thực sự coi work log chỉ tồn tại trong vòng đời Task và được phép mất.
- **Thay đổi mô hình tham chiếu**, chẳng hạn giữ snapshot thông tin Task trong lịch sử nếu phù hợp.

Không nên phản ứng với lỗi FK bằng cách tự động bật `CascadeType.ALL` trên mọi association. Cascade REMOVE có thể làm mất dữ liệu lịch sử đáng giữ hoặc xóa entity được nhiều phần khác tham chiếu.

### 19.1. Lỗi có thể chỉ xuất hiện tại flush hoặc commit

```java
Task task = em.find(Task.class, 101L);
em.remove(task);

// Không có lỗi ngay ở remove() không chứng minh DELETE sẽ thành công.
em.flush(); // Có thể phát sinh lỗi FK.
```

Nếu constraint được kiểm tra ở commit hoặc provider trì hoãn SQL, lỗi có thể xuất hiện tại `tx.commit()`. Do đó service phải xử lý transaction chứ không chỉ bắt exception quanh đúng lời gọi `remove()`.

### 19.2. Sau lỗi database/transaction, đừng tiếp tục như chưa có gì xảy ra

Với lỗi persistence nghiêm trọng như constraint violation hoặc optimistic locking, transaction có thể đã bị đánh dấu rollback-only. Không nên bắt lỗi rồi tiếp tục thực hiện thay đổi khác và cố commit như thông thường.

Cách an toàn thường là rollback khi cần, kết thúc persistence context/đơn vị công việc và khởi tạo một transaction mới nếu nghiệp vụ có phương án phục hồi.

## 20. Spring Data JPA: deleteById, getReference và transaction

Trong ứng dụng Spring Boot dùng Spring Data JPA, repository có API tiện ích như:

```java
import org.springframework.data.jpa.repository.JpaRepository;

public interface TaskRepository
        extends JpaRepository<Task, Long> {
}
```

Các phương thức thường dùng:

- `findById(id)`: trả `Optional<Task>`.
- `delete(entity)`: yêu cầu xóa entity theo cơ chế repository/JPA tương ứng.
- `deleteById(id)`: yêu cầu xóa theo ID, với chi tiết thực thi và xử lý ID không tồn tại phụ thuộc phiên bản Spring Data JPA.
- `getReferenceById(id)`: nhận reference theo ID mà **không bảo đảm kiểm tra tồn tại ngay**.

### 20.1. Ưu tiên contract rõ ràng khi cần phân biệt not found

Ví dụ service:

```java
package com.example.tasks;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class TaskService {
    private final TaskRepository tasks;

    public TaskService(TaskRepository tasks) {
        this.tasks = tasks;
    }

    @Transactional
    public boolean deleteIfExists(Long id) {
        return tasks.findById(id)
            .map(task -> {
                tasks.delete(task);
                return true;
            })
            .orElse(false);
    }
}
```

Ví dụ cho thấy lựa chọn nghiệp vụ: **không tìm thấy → trả `false`**. Nếu tìm thấy, repository yêu cầu xóa. Transaction do Spring quản lý và commit xảy ra khi phương thức kết thúc thành công qua transaction interceptor; exception tại commit có thể được ném tới caller.

Không nên giả định kết quả `true` được quyết định trước commit là chứng minh tài nguyên chắc chắn đã bị xóa: vẫn có thể gặp conflict/constraint ở thời điểm commit. Phải để transaction propagation và exception handling được xử lý đúng ở ranh giới service/caller.

### 20.2. Vì sao không nên đoán hành vi deleteById() cho mọi phiên bản?

Các phiên bản Spring Data JPA có thể khác nhau về cách triển khai và xử lý xóa ID không tồn tại. Thay vì dựa vào một hành vi exception cụ thể mà chưa xác nhận phiên bản thư viện của dự án, hãy định nghĩa **hợp đồng nghiệp vụ độc lập**:

- Nếu không tồn tại, trả `false` hoặc ném ngoại lệ ứng dụng `TaskNotFoundException`.
- Nếu tồn tại, gọi delete trong transaction.
- Nếu xảy ra concurrency conflict, xử lý riêng.
- Nếu có ràng buộc dữ liệu phụ thuộc, trả lỗi nghiệp vụ thích hợp.

Dùng `findById`/`EntityManager.find` khi cần thông báo “không tồn tại” rõ ràng, thay vì kỳ vọng một phương thức xóa tiện ích sẽ diễn đạt đúng mọi trường hợp.

### 20.3. getReferenceById không xác nhận sự tồn tại

`getReferenceById(id)` của Spring Data JPA có ý nghĩa tham chiếu tương tự `EntityManager.getReference()`. Nó có thể không truy vấn ngay và có thể thất bại khi proxy được truy cập. Vì vậy, không nên dùng nó để kiểm tra sự tồn tại trước khi trả HTTP 200 hay 204.

## 21. Thiết kế HTTP API khi tài nguyên đã bị xóa

Với một REST API:

```text
DELETE /api/tasks/101
```

Ứng dụng cần phân biệt **hợp đồng HTTP** với **cách JPA lưu trữ**.

### 21.1. Một số lựa chọn phản hồi

| Tình huống | Phản hồi có thể chọn | Lý do |
| --- | --- | --- |
| Task tồn tại và xóa thành công | `204 No Content` | Xóa thành công, không cần trả body. |
| Task không tồn tại, API báo rõ thiếu tài nguyên | `404 Not Found` | Caller được thông báo ID không có tài nguyên theo ngữ cảnh API. |
| Task không tồn tại, API coi DELETE là idempotent no-op | `204 No Content` | Mục tiêu “không còn tài nguyên” đã được thỏa mãn. |
| Biết chắc tài nguyên đã bị loại bỏ vĩnh viễn, có chính sách tombstone | `410 Gone` | Chỉ dùng khi API thực sự có thông tin về trạng thái bị xóa và muốn diễn đạt điều đó. |
| Dữ liệu đã bị sửa/xóa giữa hai thao tác với version cũ | Có thể `409 Conflict` hoặc phản hồi precondition như `412 Precondition Failed` nếu dùng `If-Match` | Xử lý xung đột theo hợp đồng API và ETag/version. |
| Task còn bị work log tham chiếu, không cho xóa | Thường `409 Conflict` | Việc xóa xung đột với ràng buộc nghiệp vụ hiện tại. |

**Idempotency của HTTP DELETE không có nghĩa mọi lần gọi phải trả cùng status code.** Nó có nghĩa lặp lại cùng yêu cầu không làm tăng tác dụng thay đổi trạng thái tài nguyên ngoài mục tiêu xóa. API có thể chọn `204` cho lần đầu và `404` cho lần sau, tùy contract.

Không nên trả `410 Gone` chỉ vì `find()` trả `null`: từ kết quả đó, ứng dụng **không biết** ID chưa từng tồn tại hay đã từng được tạo rồi bị xóa. Muốn phân biệt cần tombstone, audit log hoặc cơ chế lưu lịch sử riêng.

### 21.2. DTO/command thay vì nhận nguyên entity detached

Endpoint chỉ nên nhận ID, hoặc thêm expected version nếu concurrency contract yêu cầu:

```text
DELETE /api/tasks/101
If-Match: "version-2"
```

Service sẽ tải và kiểm tra managed entity, quyền xóa, version và các ràng buộc trước khi gọi remove. Tránh nhận một JSON object `Task` hoàn chỉnh từ client rồi gọi `merge()`/`remove()` không kiểm soát, vì có thể chứa association và dữ liệu cũ.

### 21.3. Security cũng là một phần của “không tìm thấy”

Khi tài nguyên thuộc tenant hoặc người dùng nhất định, **tồn tại trong database** chưa đủ để trả về cho caller. Ví dụ Task#101 có thể tồn tại nhưng thuộc một tenant khác. Query nên có điều kiện quyền truy cập/tenant phù hợp, và API có thể chủ động trả `404` để không tiết lộ sự tồn tại của tài nguyên, tùy chính sách bảo mật.

Không nên dựa vào `find(Task.class, id)` đơn thuần mà bỏ qua authorization.

## 22. Kiểm tra tồn tại: exists, count và race condition

Một mẫu thường thấy:

```java
if (taskRepository.existsById(id)) {
    taskRepository.deleteById(id);
}
```

Mẫu này có ít nhất hai vấn đề:

1. **Hai lần truy cập database** trong khi nhiều khi chỉ cần một query/delete hợp lý.
2. **Race condition:** sau `existsById`, transaction khác có thể xóa Task trước `deleteById`.

`existsById` cho biết điều kiện tại thời điểm đọc, không khóa hàng đến thời điểm xóa.

Nếu ứng dụng không cần phân biệt các trạng thái chi tiết, một câu bulk DELETE trả affected rows có thể là lựa chọn hiệu quả, nhưng phải chấp nhận giới hạn về callbacks/cascade/version. Nếu cần vòng đời entity, version, authorization và business rules, `find → remove` trong transaction phù hợp là lựa chọn dễ kiểm soát hơn.

### 22.1. Lựa chọn lock khi cần bảo vệ quyết định xóa

Nếu xóa Task chỉ khi không còn một điều kiện tranh chấp, cân nhắc:

```java
Task task = em.find(
    Task.class,
    id,
    jakarta.persistence.LockModeType.PESSIMISTIC_WRITE
);
```

Đây là ví dụ tìm kèm pessimistic write lock trong transaction khi hỗ trợ. Nó có thể giúp ngăn cập nhật đồng thời lên hàng mục tiêu nhưng không thay thế khóa/constraint cho những điều kiện liên quan đến nhiều hàng, và có thể làm tăng deadlock/lock wait.

Không nên dùng pessimistic lock chỉ để xử lý một thao tác xóa đơn giản mà không có nhu cầu nhất quán tương ứng.

## 23. Dữ liệu cũ trong cache và persistence context

JPA có hai khái niệm thường bị gọi chung là “cache”:

- **Persistence Context/first-level cache:** phạm vi một EntityManager; lưu các managed entity và theo dõi thay đổi.
- **Second-level cache** (nếu provider bật): có thể chia sẻ dữ liệu entity giữa nhiều persistence contexts và được provider quản lý theo quy tắc caching.

Khi một entity bị xóa qua `EntityManager.remove()` trong transaction, provider có thể cập nhật/loại bỏ dữ liệu cache tương ứng theo các quy tắc của nó.

Nhưng khi xóa bằng:

- Native SQL chạy bên ngoài JPA.
- Một job database trực tiếp.
- Database `ON DELETE CASCADE`.
- Bulk JPQL/SQL với những giới hạn state synchronization.

thì **managed entity đã tải trước đó vẫn có thể cũ**. Tùy provider/cache configuration, second-level cache cũng có thể cần cơ chế eviction/synchronization phù hợp.

### 23.1. clear, refresh và close có ý nghĩa khác nhau

| Phương thức | Ý nghĩa khi dữ liệu bị xóa ở database |
| --- | --- |
| `em.refresh(entity)` | Cố tải lại trạng thái cho managed entity; nếu hàng mất có thể thất bại. |
| `em.clear()` | Tách tất cả managed entities; một `find()` sau đó có cơ hội tải lại theo context hiện tại. |
| `em.detach(entity)` | Tách một managed entity; object cũ vẫn tồn tại trong Java. |
| `em.close()` | Đóng application-managed EntityManager, kết thúc phạm vi context tương ứng. |
| `emFactory.getCache().evict(Task.class, id)` | Yêu cầu xử lý entry trong second-level cache của JPA khi hỗ trợ; **không thay thế clear** trên persistence context hiện tại. |

**Clear/close không phải lệnh xóa database.** Refresh cũng không tự xóa hàng. Mỗi phương thức xử lý một vấn đề state/lifecycle khác nhau.

### 23.2. Một EntityManager mới chưa chắc thay thế transaction design

Đóng EntityManager cũ rồi mở cái mới có thể tránh first-level cache cũ, nhưng vẫn phải xét:

- Transaction và mức isolation.
- Second-level cache và provider.
- Dữ liệu chưa commit từ transaction khác.
- Quy tắc tenant, filtering và soft delete.

Không nên dùng giải pháp “mở context mới liên tục” thay thế cho thiết kế transaction rõ ràng.

## 24. Điều gì xảy ra nếu rollback sau remove?

Ví dụ:

```java
tx.begin();

Task task = em.find(Task.class, 101L);
em.remove(task);
em.flush();

// Có lý do nghiệp vụ phải hủy giao dịch:
tx.rollback();
```

Nếu database transaction rollback thành công, thao tác DELETE đã thực thi trong transaction **không được commit**. Hàng có thể vẫn tồn tại trong database sau rollback, tùy những transaction khác và điều kiện thực tế.

Tuy nhiên, không nên nghĩ object `task` trong bộ nhớ sẽ tự chuyển ngược hoàn toàn về trạng thái managed sạch như trước khi remove. Sau rollback, persistence context và các instance có thể không còn phản ánh đúng state database. Với application-managed EntityManager, cách an toàn thường là **kết thúc context lỗi và tải lại trong một transaction mới**.

Một tình huống tương tự là `tx.commit()` thất bại vì constraint. Sau khi transaction bị rollback, đừng tiếp tục gửi thao tác khác trên EntityManager lỗi như thể không có gì xảy ra.

### 24.1. Không trộn rollback và khôi phục tài nguyên nghiệp vụ

Rollback transaction xóa chưa commit khác với **khôi phục entity đã bị xóa và commit từ trước**.

Nếu một task đã bị xóa và transaction commit thành công, sau đó người dùng bấm “Undo”, rollback của một transaction mới **không mang hàng cũ trở lại**. Hệ thống cần một trong các giải pháp:

- Soft delete và restore.
- Lưu bản sao/tombstone đủ dữ liệu để dựng lại entity.
- Event sourcing hoặc audit/history phục vụ phục hồi.
- Một thao tác tạo mới có quy tắc ID/relationship rõ ràng.

Không nên khôi phục một entity bằng cách tái sử dụng tùy ý instance removed đã bị commit, vì JPA identity, foreign key và generator có thể không cho phép coi đó là cùng hàng cũ.

## 25. Cơ chế lỗi và cách phản hồi phù hợp

Một số ngoại lệ thường liên quan đến tình huống đã xóa/không tồn tại:

| Ngoại lệ / tình huống | Nguồn thường gặp | Ý nghĩa cần kiểm tra |
| --- | --- | --- |
| `EntityNotFoundException` | Truy cập reference của entity không còn hàng; refresh không thấy hàng. | Hàng được tham chiếu không tồn tại theo state được đọc. |
| `IllegalArgumentException` | `remove()` với detached entity; tham số không hợp lệ với API JPA. | Lỗi dùng API hoặc lifecycle. |
| `OptimisticLockException` | Update/delete với version cũ, xung đột đồng thời. | State của entity đã thay đổi hoặc hàng mất kể từ khi được đọc. |
| `TransactionRequiredException` | Thao tác ghi/lock cần transaction nhưng không có. | Ranh giới transaction sai. |
| `PersistenceException` hoặc exception provider | Constraint FK, lỗi DB, mismatch schema, vấn đề thực thi. | Cần xem nguyên nhân gốc, rollback và phân loại lỗi. |
| `NoResultException` | JPQL `getSingleResult()` không có hàng. | Không có kết quả phù hợp, khác với entity removed. |
| `NonUniqueResultException` | JPQL `getSingleResult()` có nhiều hàng. | Điều kiện truy vấn không xác định duy nhất một kết quả. |

Không nên dùng một catch tổng quát:

```java
catch (Exception ex) {
    return false; // "Task không tồn tại"
}
```

vì lỗi FK, lỗi kết nối hoặc optimistic conflict không có nghĩa task không tồn tại. Nó còn có thể khiến transaction rollback không đúng hoặc che lỗi vận hành.

Một hướng xử lý tốt hơn:

- **Không tìm thấy:** kết quả `find() == null` hoặc `Optional.empty()` được biến thành trạng thái nghiệp vụ rõ.
- **Không được phép xóa:** trả lỗi authorization/validation.
- **Có dữ liệu phụ thuộc:** trả lỗi conflict nghiệp vụ, hoặc thiết kế cascade/soft-delete nếu đúng domain.
- **Xung đột concurrent:** phân loại optimistic/locking conflict và định nghĩa chính sách retry/reload.
- **Database/transaction failure:** rollback và báo lỗi hệ thống phù hợp, không tuyên bố xóa thành công.

## 26. Các sai lầm thường gặp

### Sai lầm 1 — Nghĩ remove() xóa ngay lập tức

`em.remove(task)` đánh dấu removed; DELETE có thể chỉ chạy ở flush/commit. Một lỗi xóa có thể xuất hiện muộn.

### Sai lầm 2 — Nghĩ Java object biến mất sau remove()

Biến Java vẫn giữ object; getter có thể trả field cũ. Object đó không đại diện cho một entity hoạt động sau khi đã removed.

### Sai lầm 3 — Gọi remove() trực tiếp trên detached entity

JPA cần managed entity. Tải lại bằng `find()` và dùng object managed hiện tại.

### Sai lầm 4 — Gọi getReference() để kiểm tra tồn tại

Reference có thể không truy vấn ngay. Không có exception tại thời điểm lấy proxy **không chứng minh hàng tồn tại**.

### Sai lầm 5 — Gọi find() lần nữa trong cùng context và coi đó là refresh database

Persistence context có thể trả lại managed instance cũ. Cần phân biệt identity map với đọc lại dữ liệu ở DB.

### Sai lầm 6 — Bắt mọi exception thành “not found”

`OptimisticLockException`, FK violation và lỗi mạng không phải `find() == null`. Cần phân loại và rollback chính xác.

### Sai lầm 7 — Xóa cha và nghĩ JPA tự xóa mọi con

`@OneToMany` mặc định không cascade REMOVE. Ràng buộc FK có thể khiến xóa cha thất bại.

### Sai lầm 8 — Bật CascadeType.ALL để tránh lỗi FK

`ALL` có `REMOVE` và có thể xóa entity chia sẻ ngoài ý muốn. Chỉ cascade đúng vòng đời sở hữu.

### Sai lầm 9 — Nhầm orphanRemoval với cascade REMOVE

Orphan removal xử lý child bị loại khỏi association; cascade REMOVE lan truyền khi entity nguồn bị remove. Hai cơ chế có điểm giao nhưng khác trigger.

### Sai lầm 10 — Bulk DELETE nhưng vẫn dùng managed entities đã tải

Bulk DML bỏ qua synchronization của persistence context. Object cũ có thể mang dữ liệu đã xóa; cần clear/reload theo thiết kế.

### Sai lầm 11 — Coi soft delete là JPA removed

Soft delete là thay đổi một field nghiệp vụ trong hàng còn tồn tại. JPA removed là trạng thái lifecycle yêu cầu xóa entity.

### Sai lầm 12 — Nghĩ @Version bảo đảm không có bất kỳ race nào

`@Version` hỗ trợ optimistic locking trên entity; invariant xuyên nhiều hàng/aggregate còn cần kiểm soát transaction/concurrency riêng.

### Sai lầm 13 — Gửi sự kiện “đã xóa” ngay trong @PreRemove

Callback có thể chạy trước commit. Nếu transaction rollback, sự kiện đã gửi trở thành không đúng sự thật.

### Sai lầm 14 — Bỏ qua trạng thái sau rollback

Sau transaction lỗi/rollback, không nên tiếp tục coi những object đã removed như managed state sạch. Hãy kết thúc context hoặc tải lại có chủ đích.

### Sai lầm 15 — Trả 410 chỉ vì ID không tồn tại

`find() == null` không cho biết bản ghi chưa từng tồn tại hay đã được xóa. Muốn `410 Gone` cần có thông tin lịch sử/tombstone và chính sách API phù hợp.

## 27. Bài tập tình huống

### Bài tập 1 — Xóa ID không tồn tại

```java
Task task = em.find(Task.class, 999_999L);
if (task != null) {
    em.remove(task);
}
```

**Câu hỏi:** Khi ID không tồn tại, có lỗi gì mặc định phải phát sinh từ `find()` không?

**Giải thích:** `find()` có thể trả `null`. Ứng dụng nên quyết định contract nghiệp vụ: không tồn tại là no-op hay trả not found. Không nên gọi `remove(null)`.

### Bài tập 2 — Lặp xóa cùng ID qua hai request

Request đầu xóa Task#101 và commit. Request thứ hai bắt đầu sau đó, mở persistence context mới và gọi `find(101)`.

**Giải thích:** Lần thứ hai có thể nhận `null`. API có thể trả `204` (idempotent no-op) hoặc `404` tùy hợp đồng; không cần dựng một entity giả để xóa.

### Bài tập 3 — Hai transaction cùng giữ Task#101

A và B cùng đọc version 2. A xóa thành công rồi commit; B sau đó cố sửa title.

**Giải thích:** Với `@Version`, B có thể gặp optimistic locking conflict vì hàng không còn tồn tại. Cần rollback, reload hoặc báo conflict; không đơn giản coi cập nhật thành công.

### Bài tập 4 — getReference() đến Task#500 không có thật

```java
Task reference = em.getReference(Task.class, 500L);
System.out.println(reference.getTitle());
```

**Giải thích:** Provider có thể ném `EntityNotFoundException` lúc lấy reference hoặc khi truy cập field cần tải dữ liệu. Lấy reference không phải phép thử sự tồn tại.

### Bài tập 5 — Bulk DELETE một task đang managed

```java
Task task = em.find(Task.class, 101L);

em.createQuery("DELETE FROM Task t WHERE t.id = 101")
  .executeUpdate();

System.out.println(task.getTitle());
```

**Giải thích:** Object vẫn có thể giữ title cũ dù hàng database đã bị xóa. Bulk JPQL không đồng bộ managed state. Cần thiết kế clear/reload hoặc tránh trộn bulk delete với managed entity đang được sử dụng.

### Bài tập 6 — Xóa Project có Task tham chiếu

Project#10 có hai Task với FK không cho null, nhưng mapping không cascade remove và database không có `ON DELETE CASCADE`.

**Giải thích:** `remove(project)` có thể dẫn đến lỗi FK tại flush/commit. Cần chọn chính sách: chặn xóa, chuyển task, xóa con trước hoặc soft delete; không mặc định bật cascade ALL.

### Bài tập 7 — Xóa mềm Task

Task#101 có `deletedAt = 2027-01-05T09:00:00` nhưng hàng vẫn tồn tại.

**Giải thích:** `find(101)` theo mapping JPA thông thường vẫn có thể tìm thấy Task. Chỉ hệ thống truy vấn/soft-delete policy mới quyết định ẩn dữ liệu khỏi API. Đây không phải JPA removed state.

### Bài tập 8 — Xóa rồi rollback

Service gọi remove và flush, sau đó xảy ra lỗi dẫn đến rollback.

**Giải thích:** DELETE chưa commit có thể được hoàn tác ở database. Nhưng không nên tiếp tục dùng object/context như thể Java state tự quay về managed sạch. Tạo đơn vị công việc mới và đọc lại nếu cần.

## 28. Câu hỏi tự kiểm tra

**1. `remove()` trả về bình thường có bảo đảm hàng đã bị xóa bền vững không?**

Không. SQL có thể đang chờ flush; commit còn có thể thất bại hoặc transaction rollback.

**2. Entity removed còn tồn tại dưới dạng Java object không?**

Có thể vẫn tồn tại trong heap và được tham chiếu. Nhưng nó đã ở trạng thái removed theo JPA, không đại diện cho entity đang hoạt động.

**3. Xóa một detached entity nên bắt đầu thế nào?**

Trong transaction/context phù hợp, tìm entity managed theo ID và chỉ gọi `remove()` nếu thực sự tồn tại và được phép xóa.

**4. `find()` và `getReference()` khác nhau khi ID không tồn tại ra sao?**

`find()` có thể trả `null`. `getReference()` có thể trả proxy/reference và chỉ báo thiếu hàng khi truy cập; một số provider báo sớm.

**5. Vì sao object managed vẫn có title sau khi transaction khác xóa hàng?**

Vì persistence context giữ state Java; nó không tự đồng bộ liên tục với mọi transaction khác.

**6. `@Version` giúp phát hiện tình huống xóa đồng thời thế nào?**

Provider có thể kiểm tra version khi update/delete; nếu hàng mất hoặc version không khớp, có thể phát sinh optimistic locking conflict.

**7. Bulk JPQL DELETE có gọi `@PreRemove` cho từng entity không?**

Không như thao tác entity `remove()` thông thường. Bulk DML bỏ qua lifecycle callbacks/cascade JPA của từng entity.

**8. Xóa Project với FK từ Task có tự xóa mọi Task không?**

Không nếu chưa có cascade/DB cascade hoặc xử lý con riêng. FK có thể từ chối xóa Project.

**9. Soft delete có tương đương gọi `EntityManager.remove()` không?**

Không. Soft delete là cập nhật trạng thái nghiệp vụ, còn remove là chuyển trạng thái JPA để yêu cầu xóa vật lý.

**10. Sau rollback do delete lỗi, có nên giữ EntityManager và object removed để tiếp tục thao tác không?**

Không nên coi state đó là đáng tin. Thường cần kết thúc context/transaction rồi tải lại trong một đơn vị công việc mới.

**11. HTTP DELETE có bắt buộc trả 404 khi lặp lại không?**

Không. API có thể chọn 404 hoặc 204 theo hợp đồng, miễn hành vi an toàn và nhất quán. Idempotency không bắt buộc cùng status code ở mọi lần.

**12. Vì sao không nên kiểm tra tồn tại bằng `existsById` rồi mặc định xóa sẽ thành công?**

Vì hàng có thể bị xóa bởi transaction khác giữa hai thao tác. Cần xử lý xung đột và lỗi tại flush/commit.

## 29. Ghi nhớ cốt lõi

**Một entity bị đánh dấu `removed` trong JPA không nhất thiết đã bị DELETE ngay tại database; một hàng đã bị DELETE trong database cũng không khiến mọi Java object cũ tự biến mất.** Đó là hai lớp trạng thái cần được phân biệt: **vòng đời entity trong persistence context** và **sự tồn tại của hàng dưới các quy tắc transaction/isolation**.

Khi cần xóa một entity, luồng dễ kiểm soát là **tải managed entity bằng `find()`, kiểm tra tồn tại/quyền/ràng buộc, gọi `remove()` trong transaction và xử lý kết quả ở flush/commit**. Không gọi remove trực tiếp trên detached entity; không xem `getReference()` là phép xác minh tồn tại. Khi hàng bị transaction khác xóa, cần xử lý stale state, optimistic locking và reload theo ngữ cảnh. Khi dùng bulk SQL/JPQL, phải nhận thức rằng persistence context và callbacks/cascade JPA không tự được đồng bộ.

Cuối cùng, quyết định **xóa vật lý, xóa mềm, chặn xóa vì dữ liệu phụ thuộc, cascade hay trả not found** là quyết định của domain và API, không chỉ của một annotation. Hiểu đúng entity lifecycle, transaction và ràng buộc database sẽ giúp xử lý an toàn cả những entity đã xóa lẫn các ID không còn dữ liệu tương ứng.
