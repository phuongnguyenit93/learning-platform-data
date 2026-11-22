# Java Phaser: Phân biệt arrive() và arriveAndAwaitAdvance()

## 1. Vấn đề: “đã đến điểm đồng bộ” khác với “đợi tất cả cùng đến”

Một nhóm worker xử lý dữ liệu theo từng vòng. Ở vòng thứ nhất, mỗi worker cần tính xong một phần dữ liệu, thông báo đã hoàn tất rồi mới để nhóm bắt đầu vòng thứ hai. Nhưng không phải worker nào cũng cần đứng chờ ngay khi báo đã xong. Có worker cần **ghi nhận đã đến** rồi tiếp tục làm công việc độc lập; worker khác phải **dừng tại hàng rào** cho tới khi mọi bên tham gia đều đến.

`java.util.concurrent.Phaser` giải quyết bài toán đồng bộ theo nhiều **pha** (*phase*), với số **bên tham gia đã đăng ký** (*registered parties*) có thể thay đổi qua thời gian. Hai phương thức cốt lõi:

- **`arrive()`**: ghi nhận **một party đã đến trong pha hiện tại**, không đứng chờ các party còn lại. Trả về **số pha mà lượt đến được ghi nhận** (hoặc số âm nếu Phaser đã kết thúc).
- **`arriveAndAwaitAdvance()`**: ghi nhận party đã đến **và chờ** cho đến khi pha tiến lên hoặc Phaser kết thúc. Có tác dụng tương đương **`awaitAdvance(arrive())`**. Trên lộ trình bình thường, lời gọi chỉ trở lại sau khi pha đã chuyển; với pha ban đầu 0, kết quả quan sát được là 1 sau khi cả nhóm đến. Khi terminated, kết quả là số pha âm theo hợp đồng.

Đây **không** phải hai tên gọi thay thế cho nhau: chúng khác nhau ở việc có chờ tại barrier hay không, và cách bố trí pipeline công việc.

Phần này thuộc chủ đề **Phaser** của Java 7. `Phaser`, `arrive`, `arriveAndAwaitAdvance`, `awaitAdvance` và `arriveAndDeregister` ra đời từ **Java 7** và vẫn là API chuẩn trong các JDK hiện đại, không bị deprecated. Chương trình thực hành bên dưới dùng các cú pháp Java hiện đại, kiểm thử bằng **JDK 17**.

### Bạn sẽ học được

1. Hiểu các trạng thái `registered`, `arrived`, `unarrived`, `phase` và điều kiện chuyển pha.
2. Dùng `arrive()` khi chỉ muốn ghi nhận sự kiện đến mà **không tự chặn caller**.
3. Dùng `arriveAndAwaitAdvance()` làm hàng rào đồng bộ cuối mỗi vòng.
4. Tách `arrive()` và `awaitAdvance(...)` khi cần thêm logic giữa hai bước hoặc có timeout/interruption.
5. Biết vì sao `awaitAdvance` đơn lẻ **không** ghi nhận một party đã đến.
6. Quản lý đăng ký/hủy đăng ký đúng lúc và tránh double arrival.
7. Xử lý hỏng task, chờ vô hạn, timeout, interrupt và kết thúc Phaser.
8. Diễn giải số pha trả về, trạng thái snapshot và quy tắc memory visibility.
9. Chạy mã Java 17 tự kiểm chứng tất cả những hành vi quan trọng.

## 2. Các thành phần cốt lõi của một Phaser

Hãy bắt đầu bằng:

```java
import java.util.concurrent.Phaser;

Phaser phaser = new Phaser(3);
```

Đây là đoạn khởi tạo có thể dùng trong một phương thức/class Java, với ba **registered parties** ban đầu. Không có ba đối tượng `Thread` nào được tạo tự động: `3` chỉ là **số lượt arrival được yêu cầu** để pha hiện tại kết thúc, theo giao thức do ứng dụng đảm bảo.

Một Phaser có các trạng thái:

| Thành phần | Ý nghĩa | Cách quan sát |
| --- | --- | --- |
| `phase` | Vòng đồng bộ hiện tại, bắt đầu từ 0 | `getPhase()` |
| `registered parties` | Tổng số party đã đăng ký | `getRegisteredParties()` |
| `arrived parties` | Số party đã báo đến trong pha hiện tại | `getArrivedParties()` |
| `unarrived parties` | Số party chưa báo đến trong pha hiện tại | `getUnarrivedParties()` |
| `terminated` | Phaser đã kết thúc; chờ sẽ được giải phóng | `isTerminated()` |

Với `new Phaser(3)` ở pha 0:

```text
registered = 3
arrived    = 0
unarrived  = 3
phase      = 0

Party A gọi arrive(): unarrived còn 2
Party B gọi arrive(): unarrived còn 1
Party C gọi arrive(): unarrived về 0 -> chuyển sang phase 1

Ngay sau khi pha tiến lên (nếu số đăng ký không đổi):
registered = 3
arrived    = 0
unarrived  = 3
phase      = 1
```

Phaser chuyển pha khi **tất cả party còn cần arrival của pha đó đã đến**. Đối với `Phaser` mặc định, nếu số registered parties trở thành 0 do `arriveAndDeregister`, `onAdvance` mặc định sẽ kết thúc Phaser.

### 2.1. “Party” không đồng nghĩa với “thread”

Khác với việc gắn một ID đăng ký vào từng luồng, `Phaser` quản lý **số lượng** party. Nó không giữ danh sách thread đăng ký hay tự xác nhận “thread A đã gọi arrive pha này rồi”. Theo Javadoc, gọi phương thức arrival từ một party chưa đăng ký là **lỗi sử dụng**, nhưng có thể chỉ bị phát hiện muộn, nếu có.

Do đó:

- Ứng dụng phải xác định mỗi party là một worker/task/coordinator nào.
- Không để một party gọi `arrive` hai lần trong **cùng pha**.
- Không dùng `arriveAndAwaitAdvance` sau `arrive` của cùng party trong pha chưa chuyển: hành động thứ hai lại đếm thêm một lượt đến.
- Không để một party đã deregister tiếp tục tham gia arrival như còn đăng ký.
- Không dùng `getRegisteredParties()` như một bảng đăng ký danh tính task.

**Số lượng party phải phản ánh đúng giao thức nghiệp vụ**; Phaser không tự kiểm tra điều này cho bạn.

### 2.2. Khởi tạo có và không có party

```java
Phaser empty = new Phaser();
Phaser pair = new Phaser(2);
```

`new Phaser()` bắt đầu với **0 registered parties**, pha 0; cần `register()` trước khi party được phép gọi arrival. Đừng gọi `arrive` trên Phaser chưa đăng ký và kỳ vọng nó được coi là một lượt hợp lệ.

`new Phaser(2)` có hai party đã đăng ký ngay từ đầu. Hai party đó có thể được đại diện bằng hai worker, hoặc worker và main coordinator. Nếu main cũng gọi `arriveAndAwaitAdvance`, main **phải được tính trong số registered parties**.

### 2.3. Giá trị giám sát là snapshot

`getPhase`, `getRegisteredParties`, `getArrivedParties`, `getUnarrivedParties` phù hợp cho quan sát và debug, nhưng có thể thay đổi tức thì khi các luồng khác gọi `arrive`, `register` hoặc `arriveAndDeregister`.

Không xây thuật toán điều phối chỉ dựa trên:

```java
if (phaser.getUnarrivedParties() == 1) {
    // Không thể suy chắc rằng mình mãi là party cuối cùng.
}
```

Đây là đoạn minh họa cảnh báo race; không được xem snapshot là một khóa loại trừ lẫn nhau.

## 3. `arrive()`: thông báo đến, không chờ

Chữ ký:

```java
public int arrive()
```

Đây là **chữ ký API**, không phải phương thức cần tự viết lại.

Ý nghĩa:

1. Ghi nhận một lượt đến của một party trong pha hiện tại.
2. Giảm số `unarrived parties` của pha đó.
3. Nếu đây là lượt đến cuối cùng, Phaser có thể gọi `onAdvance` và tiến sang pha tiếp theo.
4. **Không chờ** các party khác đến; caller có thể tiếp tục ngay sau khi ghi nhận. Tuy nhiên việc kích hoạt `onAdvance` của bên cuối cùng có thể mất thời gian nếu callback được cài đặt lâu: không hiểu “không chờ party khác” thành cam kết phương thức luôn tức thời trong mọi trường hợp.
5. Trả về **số pha mà lượt arrival đã áp dụng**, hoặc số âm nếu Phaser terminated.

### 3.1. Ví dụ một party đến sớm

```java
Phaser p = new Phaser(2);
int oldPhase = p.arrive();

System.out.println(oldPhase);
System.out.println(p.getPhase());
System.out.println(p.getUnarrivedParties());
```

Đây là đoạn minh họa **chạy tuần tự khi chưa có party thứ hai đến**; output:

```text
0
0
1
```

Party thứ nhất đã đến pha 0, nhưng pha vẫn là 0 vì còn một party chưa đến. `arrive()` **không tự đợi** party còn lại.

### 3.2. `arrive()` không deregister

Đây là nhầm lẫn phổ biến: gọi `arrive()` **không làm giảm tổng số registered parties**. Party đã đăng ký vẫn phải báo đến ở pha tiếp theo nếu Phaser còn hoạt động.

Ví dụ với `new Phaser(2)`, sau khi cả hai đã gọi arrive để chuyển sang pha 1, Phaser tiếp tục có 2 registered parties, và pha 1 cũng cần 2 lượt arrival mới chuyển tiếp.

Muốn rời hẳn những vòng sau, phải gọi `arriveAndDeregister()` đúng lúc.

### 3.3. Khi nào nên dùng `arrive()`?

Một worker cần:

- Báo đã hoàn tất dữ liệu của vòng hiện tại.
- **Tiếp tục xử lý việc độc lập** không đụng tới dữ liệu mà các worker khác chưa công bố.
- Chỉ chờ chuyển pha ở một thời điểm sau đó.

Ví dụ:

```java
int phase = phaser.arrive();

// Làm công việc độc lập với dữ liệu của pha kế tiếp.
// Không chạm shared state nếu giao thức yêu cầu barrier.

int newPhase = phaser.awaitAdvance(phase);
```

Đây là đoạn minh họa với `phaser` đã đăng ký cho party này. `awaitAdvance(phase)` có thể chặn nếu các party khác chưa đến, nhưng **không ghi thêm lượt arrival**.

### 3.4. Vì sao trả token là pha cũ?

`arrive()` trả số pha mà lượt đến của bạn **được tính cho pha đó**, không phải bảo đảm tất cả đã đến.

Cụ thể:

- Với pha 0, `arrive()` trả 0 dù nó có thể chính là lượt đến cuối làm pha chuyển sang 1.
- Nếu muốn chờ đúng lần chuyển pha vừa báo đến, gọi `awaitAdvance(arrivalPhase)`.
- Đừng gọi `awaitAdvance(phaser.getPhase())` như một lối thay thế vô điều kiện: giữa `arrive()` và `getPhase()`, pha có thể đã tiến, khiến bạn vô tình đợi **pha tiếp theo**.

Lưu đúng **return value của `arrive()`** là cách tránh race này.

## 4. `arriveAndAwaitAdvance()`: đến và chờ cùng nhau

Chữ ký:

```java
public int arriveAndAwaitAdvance()
```

Phương thức:

1. Ghi nhận party đã đến pha hiện tại, như `arrive()`.
2. Chờ cho đến khi những party còn lại hoàn tất arrival và pha tiến lên, hoặc Phaser bị terminated.
3. Quay về để caller bắt đầu bước công việc tiếp theo đã được đồng bộ.

Theo Javadoc, tác dụng tương đương:

```java
int phase = phaser.arrive();
int next = phaser.awaitAdvance(phase);
```

Đây là mô hình phân rã hai bước tương ứng với một lời gọi `arriveAndAwaitAdvance`, **không** phải lời khuyên thực hiện cả hai cách cho cùng một lượt đến.

### 4.1. Một barrier lặp được

```java
for (int round = 0; round < 3; round++) {
    doWork(round);
    int newPhase = phaser.arriveAndAwaitAdvance();

    if (newPhase < 0) {
        break; // Group đã terminated.
    }
}
```

Đây là đoạn minh họa không độc lập: `doWork` và `phaser` phải được định nghĩa, mỗi party phải được đăng ký trước, các party khác phải đến đúng số vòng. Một vòng mới chỉ được bắt đầu sau khi pha đồng bộ đã tiến.

### 4.2. Pha trả về và pha hiện tại

Trong ví dụ bình thường đã kiểm thử bằng JDK 17:

```text
Bắt đầu phase = 0
Party A: arriveAndAwaitAdvance() đang chờ
Party B: arriveAndAwaitAdvance() là lượt đến cuối

Khi cả hai trở về:
phase hiện tại = 1
giá trị trả về = 1 trên hai lời gọi
```

Trong khi đó `arrive()` được thực hiện cho cùng pha 0 sẽ trả **0**. Phân biệt **pha ghi nhận lượt đến** với **pha đạt được sau khi chờ chuyển pha** giúp tránh những lỗi off-by-one.

Khi Phaser bị kết thúc, `arriveAndAwaitAdvance()` có thể trả **số âm**, không coi giá trị đó là một pha bình thường.

### 4.3. Phương thức chờ không thể interrupt trực tiếp

`arriveAndAwaitAdvance()` **không khai báo `InterruptedException`**, và cơ chế đợi bên trong tương đương `awaitAdvance` **không dừng việc đợi chỉ vì thread bị interrupt**. Trạng thái interrupt của thread được giữ/khôi phục theo hợp đồng.

Vì vậy câu sau **không** tạo ra một barrier có timeout hoặc chờ interruptible:

```java
phaser.arriveAndAwaitAdvance();
```

Nếu cần timeout/interruption, dùng `arrive()` trước, rồi gọi `awaitAdvanceInterruptibly(phase,...)`. Chi tiết và quy trình khôi phục nằm ở mục 8.

### 4.4. Không dùng với party chưa đăng ký

Giống `arrive()`, `arriveAndAwaitAdvance()` yêu cầu caller đại diện một party đã đăng ký. Nếu chưa đăng ký hoặc đã deregister, đây là **lỗi sử dụng**; Java có thể không phát hiện ngay vì không gắn danh tính party với thread.

Không chạy “ai cũng được gọi barrier” trên một `Phaser(1)` chỉ vì compiler cho phép.

## 5. Bảng so sánh nhanh các phương thức liên quan

| API | Ghi nhận arrival? | Tự chờ pha chuyển? | Xóa đăng ký party? | Kết quả |
| --- | --- | --- | --- | --- |
| `arrive()` | **Có** | **Không** | **Không** | Pha lượt đến áp dụng, hoặc âm khi terminated |
| `arriveAndAwaitAdvance()` | **Có** | **Có** | **Không** | Kết quả sau chờ chuyển pha, hoặc âm khi terminated |
| `awaitAdvance(phase)` | **Không** | **Có**, nếu current phase vẫn bằng `phase` | **Không** | Pha đạt được hoặc giá trị âm khi terminated |
| `awaitAdvanceInterruptibly(phase, timeout, unit)` | **Không** | **Có**, ngắt được và có deadline | **Không** | Pha đạt được; có thể ném `InterruptedException`/`TimeoutException` |
| `arriveAndDeregister()` | **Có** | **Không** | **Có** | Pha arrival áp dụng, hoặc âm khi terminated |
| `register()` | **Không** | Không chờ barrier thông thường, nhưng có thể đợi `onAdvance` đang chạy | **Thêm một party** | Pha đăng ký, hoặc âm nếu terminated |
| `forceTermination()` | Không | Không; giải phóng các waiter | Không tự thay đổi count registered | Không trả về |

Điểm cần nhớ: **`awaitAdvance` chỉ đợi; `arrive` chỉ báo đến; `arriveAndAwaitAdvance` làm cả hai; `arriveAndDeregister` báo đến rồi rời nhóm.**

### 5.1. Các biến thể có thể kết hợp

Một lời gọi:

```java
int p = phaser.arrive();
int next = phaser.awaitAdvance(p);
```

về tác dụng đồng bộ cơ bản giống `arriveAndAwaitAdvance`. Nhưng cách viết tách rời cho phép:

- Thực hiện công việc độc lập giữa hai lời gọi.
- Gọi `awaitAdvanceInterruptibly` để có timeout.
- Chuyển token pha sang một component điều phối phù hợp.
- Ghi telemetry thời điểm đã đến và thời điểm barrier hoàn tất.

Cần cẩn thận: từ lúc `arrive` tới lúc pha mới, party **đã arrived**; không được thực hiện thêm một phương thức arrival trên cùng party trong pha đó.

### 5.2. Không gọi `awaitAdvance` thay cho arrival

Nếu bạn là party thứ hai của `Phaser(2)`, nhưng chỉ gọi:

```java
phaser.awaitAdvance(phaser.getPhase());
```

thì **không có lượt đến** được ghi nhận từ party này. Nếu party kia đã gọi `arriveAndAwaitAdvance` và đang đợi bạn, nhóm sẽ không tiến pha cho tới khi một party hợp lệ thực hiện arrival còn thiếu.

Một observer **không đăng ký** có thể dùng `awaitAdvance` để theo dõi pha, nhưng observer đó không được tự đếm là party cần arrival. Đây là một ứng dụng nâng cao, cần biết rõ ai chịu trách nhiệm tiến pha.

## 6. Giải thích theo timeline: hai worker và một coordinator

Giả sử `new Phaser(3)` gồm Worker A, Worker B và main coordinator:

```text
Phase 0 -- registered 3, unarrived 3

Worker A: làm A0 ---> arriveAndAwaitAdvance() ---\
Worker B: làm B0 ----------> arriveAndAwaitAdvance() --+-- đợi
Main    : kiểm tra setup -> arriveAndAwaitAdvance() ---/

Khi đã đủ 3 arrivals:
                   phase 0 -> phase 1
                   tất cả waiter tiếp tục

Phase 1 -- registered 3, unarrived 3

Worker A: làm A1 ---> arriveAndAwaitAdvance() ---\
Worker B: làm B1 ---> arriveAndAwaitAdvance() ----+-- đợi
Main    : phần việc chính -> arriveAndAwaitAdvance() -/

Khi đủ 3 arrivals:
                   phase 1 -> phase 2
```

Mỗi bên báo đến **một lần cho mỗi pha**. Nếu main chỉ là observer, có thể không đăng ký main và thay bằng `new Phaser(2)`; khi đó main có thể dùng `awaitAdvance` để theo dõi, **nhưng không được gọi arrival như party thứ ba**.

### 6.1. Khi Worker A muốn báo đến sớm rồi tiếp tục việc độc lập

Thay vì:

```java
phaser.arriveAndAwaitAdvance(); // A sẽ dừng chờ.
```

A có thể:

```java
int arrived = phaser.arrive();
performIndependentWork();
int next = phaser.awaitAdvance(arrived);
```

Đây là code minh họa, với hàm `performIndependentWork` do ứng dụng tự định nghĩa. Điều kiện quan trọng là phần việc độc lập **không phụ thuộc vào dữ liệu mà barrier cần bảo vệ**. Nếu A sửa shared state của vòng tiếp theo trước khi B đến, nó có thể phá vỡ protocol bất chấp có gọi Phaser.

### 6.2. Khi Worker A không còn làm vòng sau

A có thể `arriveAndDeregister()` thay vì `arrive()`. Lượt đến hiện tại vẫn được tính, nhưng **A không còn là party phải đến ở các pha tiếp theo**.

Không đếm số task đã hoàn tất bằng `arrive` rồi nghĩ số registered giảm theo: hai khái niệm khác nhau.

## 7. Giao thức đăng ký và hủy đăng ký

### 7.1. Đăng ký cố định

Nếu có đúng N party trong suốt tất cả vòng:

```java
Phaser phaser = new Phaser(N);
```

Đây là đoạn minh họa với `N` được khai báo và kiểm tra trước. Phải bảo đảm đúng N bên thực sự hoạt động; nếu chỉ có N-1 bên gọi arrival, barrier sẽ không tiến.

### 7.2. Đăng ký động

Phaser cho phép:

```java
Phaser phaser = new Phaser(1); // Coordinator đã đăng ký.
phaser.register();             // Một worker mới.
phaser.bulkRegister(3);        // Ba worker mới.
```

Các lời gọi đăng ký trả số pha tương ứng; có thể chờ một hành động `onAdvance` đang chạy, không nên khẳng định register luôn non-blocking tuyệt đối.

**Đăng ký trước khi submit hoặc khởi động worker**, không submit xong rồi mới register, vì worker có thể chạy trước và arrive khi chưa có slot, hoặc barrier có thể tiến trước khi bạn kịp tăng party count.

### 7.3. Một starting gate linh hoạt

Mẫu thường gặp:

```java
Phaser gate = new Phaser(1); // Coordinator.
for (Runnable task : tasks) {
    gate.register();
    executor.execute(() -> {
        int p = gate.arriveAndAwaitAdvance();
        if (p < 0) return;
        task.run();
        gate.arriveAndDeregister();
    });
}
gate.arriveAndDeregister(); // Coordinator không đứng chờ.
```

Đây là **khung ý tưởng chưa độc lập**, vì `tasks`, `executor` và quản lý lỗi/shutdown cần triển khai đầy đủ. Điểm học tập là coordinator có thể dùng `arriveAndDeregister()` để **mở cổng** cho các worker đã đăng ký, không nhất thiết đứng đợi.

**Quan trọng:** ví dụ tối giản này chưa xử lý `task.run()` ném exception khiến worker không deregister. Trong production cần `try/finally` **chỉ khi chắc chưa arrive lần nào trong pha hiện tại**, hoặc `forceTermination`/cơ chế failure propagation phù hợp. Không đơn giản nhét `arriveAndDeregister` vào mọi `finally` rồi gây double arrival.

### 7.4. Hủy đăng ký không đợi

`arriveAndDeregister()` khác `arriveAndAwaitAdvance()`:

- `arriveAndDeregister` ghi arrival, giảm registered party count và không chờ các party khác.
- `arriveAndAwaitAdvance` ghi arrival, **không giảm registered count**, và chờ pha chuyển.
- `arrive` ghi arrival, không chờ và không giảm registered count.

Khi party cuối cùng deregister trong một Phaser mặc định, `onAdvance` mặc định dẫn tới **termination**; `getPhase()` chuyển sang giá trị âm.

### 7.5. Tại sao deregister sau vòng cuối cũng cần một arrival?

Mỗi party vẫn thuộc một pha tại thời điểm rời. `arriveAndDeregister` đóng góp **một lượt đến của pha hiện tại** đồng thời hủy trách nhiệm ở những pha sau. Nếu party đã gọi `arrive` ở pha đó, **đừng gọi `arriveAndDeregister` tiếp ngay** vì sẽ là arrival thứ hai; cần đợi pha chuyển hoặc xác định lại mô hình ownership.

## 8. Khi cần timeout hoặc interruptible waiting

### 8.1. Hai bước cho phép timeout

`arriveAndAwaitAdvance()` không nhận timeout. Khi yêu cầu deadline:

```java
int phase = phaser.arrive();
try {
    int next = phaser.awaitAdvanceInterruptibly(
            phase, 5, TimeUnit.SECONDS);
    if (next < 0) {
        // Phaser đã terminated; thông báo cho workflow.
    }
} catch (TimeoutException timeout) {
    // Phải áp dụng chính sách thất bại/cancel của cả nhóm.
} catch (InterruptedException interrupted) {
    Thread.currentThread().interrupt();
    // Thông báo/khôi phục theo hợp đồng ứng dụng.
}
```

Đây là **đoạn minh họa trong phương thức**, có import `TimeUnit`, `TimeoutException` và `phaser` đã khởi tạo. Trong production, owner quyết định tiếp tục chờ, abort bằng `forceTermination`, hay chuyển trạng thái phiên xử lý.

### 8.2. Timeout không hủy arrival đã ghi nhận

Một sai lầm nguy hiểm:

> `awaitAdvanceInterruptibly(phase, timeout, unit)` timeout nên Phaser tự giảm số party hoặc xóa lượt đến.

**Sai.** Exception xảy ra trong bước **waiting**, không tự rollback `arrive()` trước đó. Party vẫn đã đăng ký, và lượt đến hiện tại vẫn được tính. Nếu các party còn lại không đến, Phaser có thể tiếp tục mắc ở pha đó.

Không cố “sửa” bằng cách gọi ngay `arriveAndDeregister()` từ cùng party trong pha chưa chuyển — như vậy có thể **đếm arrival hai lần**.

### 8.3. Recovery khi một bên thất bại

Nếu task gặp exception **trước** lượt arrival, những party khác đang đợi có thể mắc kẹt vô hạn. Tùy semantics, có thể:

1. Báo lỗi vào một kênh thread-safe.
2. Cho coordinator quyết định **`phaser.forceTermination()`** để đánh thức waiters.
3. Hủy/đóng các tác vụ nguồn liên quan theo contract.
4. Đợi tất cả workers dừng rồi phát hành kết quả lỗi tập thể.
5. Nếu muốn tiếp tục chạy với ít party hơn, phải thiết kế rõ quy trình deregistration, **không tùy tiện gọi arrival hai lần**.

`forceTermination` hữu ích cho **abort một batch**, nhưng ảnh hưởng toàn bộ parties của phaser và **không phải cách retry một request đơn lẻ vô điều kiện**.

### 8.4. `awaitAdvanceInterruptibly` có phá barrier không?

Theo Javadoc, timeout/interruption khi chờ **không tự làm thay đổi trạng thái Phaser**. Đây là điểm khác với một số synchronization primitives có broken-barrier semantics.

Vì vậy một bên timeout không bảo đảm bên khác được giải phóng. Coordinator cần chính sách phục hồi tường minh.

### 8.5. Interrupt của arriveAndAwaitAdvance

`arriveAndAwaitAdvance()` dùng lối đợi không interruptible. Nếu thread bị interrupt trong khi đợi, lời gọi vẫn có thể tiếp tục chờ tới khi pha tiến/termination; trạng thái interrupt được bảo tồn theo hợp đồng.

Đừng cố bọc:

```java
try {
    phaser.arriveAndAwaitAdvance();
} catch (InterruptedException ignored) {
    // Sai: arriveAndAwaitAdvance không khai báo InterruptedException.
}
```

Đây là **đoạn minh họa cố ý sai và không biên dịch** nếu không có lời gọi nào khác ném checked exception bên trong `try`. Muốn ứng dụng có thể dừng theo interrupt/deadline, dùng hai bước cùng `awaitAdvanceInterruptibly`.

## 9. Khi Phaser terminated

`Phaser` có thể kết thúc khi:

- `onAdvance` trả `true`, ví dụ override để dừng sau số vòng xác định.
- Với implementation mặc định, `arriveAndDeregister` làm số registered parties về 0 và xảy ra pha tiến lên.
- Owner gọi `forceTermination()`.

Sau termination:

- `isTerminated()==true`.
- `getPhase()` là **số âm** theo cách mã hóa pha terminated.
- Những phương thức chờ/trạng thái đồng bộ không còn chặn để chờ pha tiến thông thường; các lời gọi trả số âm theo hợp đồng.
- Gọi `register` không hồi sinh phaser đã terminated.
- Nếu muốn chạy một lượt mới độc lập, thường tạo **một Phaser mới**, trừ khi thiết kế có override `onAdvance` phù hợp ngay từ đầu.

```java
Phaser p = new Phaser(1);
int arrival = p.arriveAndDeregister();
boolean stopped = p.isTerminated();

System.out.println(arrival);
System.out.println(stopped);
```

Trong đoạn minh họa độc lập này, output:

```text
0
true
```

`arriveAndDeregister` trả **pha nơi lượt đến được tính** (0), còn trạng thái Phaser **sau đó** là terminated. Không coi 0 trả về ở lệnh vừa kích hoạt termination là “vẫn chưa terminated”.

### 9.1. Không so pha âm như pha bình thường

Nếu `int p = phaser.arriveAndAwaitAdvance()` trả số âm, ứng dụng nên coi đó là tín hiệu dừng/abort, thay vì dùng `p` làm index mảng hoặc vòng lặp công việc.

Một check thường gặp:

```java
int next = phaser.arriveAndAwaitAdvance();
if (next < 0) {
    return; // Dừng thao tác theo contract nghiệp vụ.
}
```

Đây là đoạn minh họa trong phương thức có kiểu trả `void`. Không bỏ qua trường hợp âm trong workflow có thể terminate.

### 9.2. Vòng quay số pha

Pha bắt đầu 0 và có thể tăng đến `Integer.MAX_VALUE` rồi **quay về 0**. Không viết logic production suy rằng số pha tăng mãi vô hạn hoặc chỉ so `current >= target` trên một tác vụ sống rất dài mà không tính đến overflow/wrap.

Trên phạm vi thử nghiệm vài vòng, số pha 0,1,2 là dễ đọc, nhưng đó là **ví dụ nhỏ**, không phải hợp đồng pha chỉ có ba giá trị.

## 10. Bộ nhớ và thứ tự dữ liệu giữa các pha

`Phaser` không chỉ để đếm: Java API mô tả hiệu ứng **happens-before** liên quan tới việc tiến pha.

Theo hợp đồng memory consistency, các hành động của party **trước** một hình thức arrival sẽ *happen-before* pha tiến và hành động `onAdvance`, và từ pha tiến sẽ *happen-before* các hành động **sau pha tiến**.

Điều này cho phép sử dụng Phaser để chia những bước xử lý phụ thuộc nhau theo pha: mỗi worker ghi dữ liệu vòng 0 vào vùng mà nó sở hữu, báo đến, chờ đủ các worker; sau barrier có thể đọc dữ liệu vòng 0 theo protocol.

### 10.1. Mẫu đúng

```java
results[workerIndex] = calculateForThisWorker();
int next = phaser.arriveAndAwaitAdvance();

if (next >= 0) {
    consumeAllResults(results);
}
```

Đây là **mã minh họa**, không phải chương trình độc lập: `results`, `workerIndex`, `calculateForThisWorker`, `consumeAllResults` cần được định nghĩa. Cần bảo đảm mỗi worker chỉ ghi vào phần dữ liệu riêng trước barrier, và mọi consumer chỉ đọc dữ liệu chung **sau khi pha đã tiến**.

### 10.2. Arrive không đồng nghĩa caller đã vượt barrier

Nếu worker A gọi `arrive()` rồi ngay lập tức đọc một vùng `results` mà worker B chưa ghi, A **chưa chờ** barrier. Happens-before thông qua tiến pha chỉ áp dụng khi thực tế đã có đồng bộ chuyển pha; lệnh `arrive()` đơn lẻ không cấp quyền đọc dữ liệu tương lai.

Vì vậy dùng `arriveAndAwaitAdvance` hoặc đợi `awaitAdvance(token)` trước khi khai thác những dữ liệu mà giao thức yêu cầu đủ cả nhóm.

### 10.3. Barrier không thay thế mọi đồng bộ khác

Nếu hai worker ghi **cùng một ô** trong shared array **trước** barrier, Phaser không tự sửa data race hoặc xác định ai thắng. Hãy phân vùng dữ liệu theo party, dùng atomic/lock khi cần, hoặc thiết kế pha rõ ràng.

Phaser bảo đảm thứ tự giữa **các giai đoạn**, không tự động làm bất kỳ truy cập mutable object nào cũng thread-safe.

## 11. Ví dụ Java 17+ đã biên dịch, chạy và kiểm chứng

Chương trình `PhaserArrivalsDemo.java` có các kiểm thử:

1. Tạo `Phaser(2)`. Party thứ nhất gọi `arrive()`; assert pha vẫn 0 và `getUnarrivedParties()==1`.
2. Party thứ hai trong executor gọi `arriveAndAwaitAdvance()`. Party thứ nhất (đã arrive) dùng **`awaitAdvanceInterruptibly(oldPhase, 5, SECONDS)`** và thấy pha 1. Party thứ hai cũng nhận kết quả 1.
3. Dùng `Phaser(3)` để đồng bộ **hai worker + main** qua hai pha. Các worker cập nhật `AtomicInteger` trước barrier; main chỉ kiểm tra sau khi mọi party đã đến. Các worker deregister sau pha thứ hai; main deregister, **party cuối cùng làm Phaser mặc định terminated**.
4. Mô phỏng một party đã arrive nhưng party thứ hai không tới. `awaitAdvanceInterruptibly(phase, 50ms)` timeout; assert lượt đến vẫn được ghi nhận. Gọi `forceTermination` và xác minh kết quả wait có pha âm.
5. Kiểm tra `arriveAndAwaitAdvance` không tự ném `InterruptedException` bằng cách interrupt một thread trước/đang chờ, sau đó để barrier tiến. Thread thoát và cờ interrupt được giữ.
6. Toàn bộ assertion chạy thành công, executor được shutdown/awaitTermination trong `finally`.

Để stdout dễ đối chiếu, **chỉ main thread in các dòng kết quả**. Worker hoàn tất có thể chạy theo nhiều thứ tự, nhưng các assertion và in kết quả không phụ thuộc thứ tự print từ worker.

### 11.1. Toàn bộ file `PhaserArrivalsDemo.java`

```java
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.Phaser;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

public final class PhaserArrivalsDemo {
    private static void check(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }

    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newFixedThreadPool(2);
        try {
            Phaser split = new Phaser(2);
            int arrivedPhase = split.arrive();
            check(arrivedPhase == 0,
                    "arrive must report the old phase");
            check(split.getPhase() == 0
                    && split.getUnarrivedParties() == 1,
                    "arrive must not wait for the other party");
            System.out.println("arrive returned phase = "
                    + arrivedPhase);
            System.out.println("phase before peer arrives = "
                    + split.getPhase());

            Future<Integer> peer =
                    executor.submit(split::arriveAndAwaitAdvance);
            int observed = split.awaitAdvanceInterruptibly(
                    arrivedPhase, 5, TimeUnit.SECONDS);
            int peerResult = peer.get(5, TimeUnit.SECONDS);
            check(observed == 1 && peerResult == 1,
                    "phase must advance after final arrival");
            System.out.println("awaitAdvance moved to = " + observed);
            System.out.println(
                    "peer arriveAndAwaitAdvance returned = " + peerResult);
            split.forceTermination();

            Phaser rounds = new Phaser(3);
            AtomicInteger stageOne = new AtomicInteger();
            AtomicInteger stageTwo = new AtomicInteger();

            Callable<int[]> worker = () -> {
                stageOne.incrementAndGet();
                int first = rounds.arriveAndAwaitAdvance();
                check(first == 1, "first advanced phase");
                stageTwo.incrementAndGet();
                int second = rounds.arriveAndAwaitAdvance();
                check(second == 2, "second advanced phase");
                rounds.arriveAndDeregister();
                return new int[] {first, second};
            };

            Future<int[]> firstWorker = executor.submit(worker);
            Future<int[]> secondWorker = executor.submit(worker);

            int round1 = rounds.arriveAndAwaitAdvance();
            check(round1 == 1 && stageOne.get() == 2,
                    "all parties must complete first stage");
            int round2 = rounds.arriveAndAwaitAdvance();
            check(round2 == 2 && stageTwo.get() == 2,
                    "all parties must complete second stage");

            rounds.arriveAndDeregister();
            int[] a = firstWorker.get(5, TimeUnit.SECONDS);
            int[] b = secondWorker.get(5, TimeUnit.SECONDS);
            check(a[0] == 1 && a[1] == 2
                    && b[0] == 1 && b[1] == 2,
                    "all workers must see both advances");
            check(rounds.isTerminated(),
                    "last deregistration terminates");
            System.out.println("two synchronized rounds = "
                    + round1 + "," + round2);
            System.out.println(
                    "last deregistration terminated = true");

            Phaser timed = new Phaser(2);
            int phase = timed.arrive();
            boolean timedOut = false;
            try {
                timed.awaitAdvanceInterruptibly(
                        phase, 50, TimeUnit.MILLISECONDS);
            } catch (TimeoutException expected) {
                timedOut = true;
            }
            check(timedOut && timed.getPhase() == 0
                    && timed.getUnarrivedParties() == 1,
                    "timeout must not undo arrival");
            timed.forceTermination();
            check(timed.isTerminated()
                    && timed.awaitAdvance(phase) < 0,
                    "forced termination releases waiters");
            System.out.println(
                    "timeout leaves arrival recorded = true");
            System.out.println(
                    "forceTermination returned negative = true");

            Phaser uninterruptible = new Phaser(2);
            CountDownLatch started = new CountDownLatch(1);
            AtomicBoolean interruptRetained = new AtomicBoolean();
            Thread thread = new Thread(() -> {
                started.countDown();
                int next = uninterruptible.arriveAndAwaitAdvance();
                interruptRetained.set(next == 1
                        && Thread.currentThread().isInterrupted());
            }, "phaser-waiter");

            thread.start();
            check(started.await(5, TimeUnit.SECONDS),
                    "waiter did not start");
            thread.interrupt();

            int mainNext = uninterruptible.arriveAndAwaitAdvance();
            thread.join(5_000L);
            check(!thread.isAlive() && mainNext == 1
                    && interruptRetained.get(),
                    "uninterruptible wait should retain interrupt status");
            System.out.println(
                    "arriveAndAwaitAdvance retained interrupt = true");

            System.out.println("checks = PASS");
        } finally {
            executor.shutdownNow();
            check(executor.awaitTermination(5, TimeUnit.SECONDS),
                    "executor did not terminate");
        }
        System.out.println("executor terminated = true");
    }
}
```

### 11.2. Biên dịch và chạy

Đảm bảo có **JDK 17+** và lưu file đúng tên class:

```bash
javac --release 17 -Xlint:all -Werror -encoding UTF-8 PhaserArrivalsDemo.java
java PhaserArrivalsDemo
```

Đã kiểm thử thực tế với lệnh strict compilation trên Java 17; **stdout đúng 11 dòng**:

```text
arrive returned phase = 0
phase before peer arrives = 0
awaitAdvance moved to = 1
peer arriveAndAwaitAdvance returned = 1
two synchronized rounds = 1,2
last deregistration terminated = true
timeout leaves arrival recorded = true
forceTermination returned negative = true
arriveAndAwaitAdvance retained interrupt = true
checks = PASS
executor terminated = true
```

### 11.3. Vì sao `arrive` không chờ?

Sau khi party đầu tiên gọi `split.arrive()`, `split.getPhase()==0` và `getUnarrivedParties()==1`. Main không đợi phía kia: nó còn chạy code in trạng thái và submit peer. Đây là minh chứng có kiểm soát rằng `arrive` không phải barrier wait.

### 11.4. Vì sao không gọi `arriveAndAwaitAdvance` sau `arrive`?

Main đã đến pha 0 qua `split.arrive()`. Nếu main lại gọi `split.arriveAndAwaitAdvance()` trước khi pha tiến, nó có thể **đếm thêm một arrival sai**, khiến Phaser nghĩ party khác đã đến.

Thay vào đó, main gọi `split.awaitAdvanceInterruptibly(arrivedPhase, ...)`, chỉ đợi pha 0 chuyển đi. Party thứ hai gọi `arriveAndAwaitAdvance` để đóng góp arrival còn thiếu.

### 11.5. Vì sao `peerResult==1`?

Peer là bên có thể khiến pha chuyển từ 0 sang 1. `arriveAndAwaitAdvance` không trả về để tiến sang bước tiếp theo trước khi pha đã hoàn thành theo giao thức. Trong JDK 17 kiểm thử, kết quả phương thức của peer là 1; `awaitAdvanceInterruptibly` của main cũng trả 1.

### 11.6. Vì sao dùng hai worker và một main ở ví dụ hai vòng?

`rounds = new Phaser(3)` có 3 parties. Hai worker thực hiện bước công việc và dừng ở barrier; main đóng góp party thứ ba qua `arriveAndAwaitAdvance`. Chỉ khi đủ ba arrivals, pha 0 chuyển 1; tương tự pha 1 chuyển 2.

Nếu main quên gọi barrier hoặc khai báo `Phaser(2)` rồi vẫn cho cả ba party gọi arrival, số đếm không còn đúng; có thể gây chờ vô hạn hoặc lỗi double arrival.

### 11.7. Vì sao deregister sau hai vòng?

Tất cả đều còn đăng ký sau `arriveAndAwaitAdvance` ở pha 0 và pha 1. Đến pha 2, nhóm không cần vòng kế tiếp nên mỗi party gọi **một lần `arriveAndDeregister`**. Party cuối khiến số registered trở về 0 và Phaser mặc định terminated.

Nếu chỉ gọi `arrive` khi kết thúc, registered count vẫn giữ 3; Phaser có thể tiếp tục chờ các vòng tương lai.

### 11.8. Vì sao timeout không “hoàn tác” arrival?

`timed.arrive()` đã giảm `unarrived` từ 2 xuống 1. Sau khi đợi 50ms không có party thứ hai đến, phương thức `awaitAdvanceInterruptibly` ném `TimeoutException`; trạng thái `phase==0` và `unarrived==1` vẫn giữ.

`forceTermination` sau đó là lựa chọn **của demo** để không để một Phaser còn đợi vô hạn; trong sản phẩm thật phải do owner quyết định ảnh hưởng tới toàn bộ group.

### 11.9. Tại sao ví dụ interrupt vẫn có kết quả?

Thread phụ gọi `arriveAndAwaitAdvance`, main phát interrupt, rồi đóng góp arrival còn lại. Vì lối đợi này không interruptible, worker không ném `InterruptedException` và có thể tiến tới pha 1; cờ interrupt được giữ. Nếu yêu cầu worker phải dừng tức thời theo interrupt, phải dùng phương thức chờ interruptible và thiết kế recovery.

### 11.10. Vì sao không dùng `Thread.sleep` để đồng bộ thứ tự?

Hai lượt chuyển pha chính dựa trên barrier thực sự, `Future.get` có timeout và các assertion. Trường hợp interrupt có `CountDownLatch` để xác nhận thread đã được khởi động trước khi gửi interrupt; không dựa vào ngủ một khoảng thời gian tùy ý.

Khoảng 50ms ở bài test timeout là **deadline cố ý**, không phải dùng sleep để mong thread sắp chạy theo lịch định sẵn.

## 12. Thiết kế một pipeline nhiều pha an toàn

Ví dụ hệ thống có các bước:

1. Worker phân tích một chunk.
2. Tất cả worker chờ hoàn tất phần phân tích.
3. Mỗi worker tổng hợp từ chunk của các bên khác.
4. Tất cả chờ hoàn tất tổng hợp.
5. Coordinator công bố kết quả và kết thúc.

Một mô hình phù hợp:

```text
Phaser registered = number of workers + coordinator

phase 0:
  worker i: analyze(chunk[i])
  all: arriveAndAwaitAdvance()

phase 1:
  worker i: merge(partial results)
  all: arriveAndAwaitAdvance()

phase 2:
  all: arriveAndDeregister()
  phaser terminates when last party deregisters
```

### 12.1. Chỉ dùng arriveAndAwaitAdvance tại ranh giới phụ thuộc

Nếu tất cả worker đều phải chờ dữ liệu trước khi tiếp tục, `arriveAndAwaitAdvance` rõ ràng, dễ bảo trì.

Nếu một worker có thêm phần việc độc lập sau khi hoàn thành stage hiện tại, có thể `arrive` trước rồi `awaitAdvance` sau. Nhưng hãy ghi rõ đâu là phần độc lập; không được đụng dữ liệu stage kế tiếp sớm.

### 12.2. Kiểm soát số parties với executor

Nếu đăng ký `N=10` workers nhưng executor chỉ có 2 threads và mỗi worker tới barrier trước khi 8 worker còn lại được schedule, hai threads đầu có thể **blocked** và các tasks còn lại không được chạy. Lỗi này không đến từ `Phaser` mà từ **thiết kế số worker/queue**.

Để chạy group barrier blocking:

- Đảm bảo có đủ threads/parallelism để **các party cần thiết có cơ hội đến**.
- Hoặc điều phối stage theo phương án không giữ những worker bị chặn.
- Không submit số lượng barrier participants lớn hơn năng lực chạy đồng thời nếu tất cả sẽ block trước khi task còn lại được schedule.
- Có chính sách deadline, shutdown và failure propagation.

Phaser có thể được dùng trong ForkJoinPool, nhưng đừng mặc định mọi cấu hình work-stealing sẽ tự chữa một vòng chờ thiếu worker.

### 12.3. Bảo đảm lifecycle trong lỗi bất ngờ

Một task thất bại trước arrival có thể khiến các party khác chờ mãi. Một quy trình khôi phục an toàn thường:

- Ghi nguyên nhân lỗi vào cấu trúc thread-safe.
- Coordinator gọi `forceTermination` khi muốn abort cả group.
- Các worker kiểm tra `next < 0` hoặc `phaser.isTerminated()` sau khi được giải phóng.
- Dừng work/rollback hoặc release resource theo policy.
- Chờ Future/threads hoàn tất; không chỉ forceTerminate rồi trả kết quả thành công.

Không dùng `forceTermination` chỉ để tiết kiệm thời gian chờ mỗi pha bình thường; nó là tín hiệu kết thúc cho toàn bộ Phaser.

### 12.4. `onAdvance` chạy ở party kích hoạt chuyển pha

Có thể override:

```java
Phaser phaser = new Phaser(3) {
    @Override
    protected boolean onAdvance(int phase, int registeredParties) {
        return phase >= 1 || registeredParties == 0;
    }
};
```

Đây là đoạn minh họa: khi đã hoàn tất pha 1, Phaser sẽ kết thúc; điều kiện `registeredParties==0` cũng giữ semantics mặc định. `onAdvance` được thực thi bởi party kích hoạt phase advance và **không nên thực hiện công việc nặng, chờ chính Phaser hoặc làm reentrant registration/arrival**. Nếu callback ném unchecked exception, việc chuyển pha có thể không xảy ra, gây tình trạng khó phục hồi.

## 13. Bẫy khi phối hợp awaitAdvance và arrive

### 13.1. Sai: dùng pha được đọc lại thay vì token

```java
phaser.arrive();
// Có thể một party khác vừa làm phase 0 -> 1.
phaser.awaitAdvance(phaser.getPhase());
```

Nếu phase đã là 1 khi `getPhase()` chạy, caller lại đợi **phase 1 -> 2**, thay vì đợi chính phase 0 đã báo đến. Trong workflow không có vòng tiếp theo, điều này có thể khiến caller bị chặn vô hạn.

Đúng:

```java
int arrivalPhase = phaser.arrive();
phaser.awaitAdvance(arrivalPhase);
```

Truyền token return từ `arrive` bảo đảm bạn đợi pha tương ứng. Nếu pha đã tiến, `awaitAdvance(arrivalPhase)` trả ngay.

### 13.2. Sai: arrive hai lần trong cùng một pha

```java
phaser.arrive();
phaser.arriveAndAwaitAdvance();
```

Nếu cùng party gọi như vậy mà pha chưa tiến, nó tự ghi nhận hai lượt đến. Java không tự gắn danh tính thread với party, nên lỗi có thể không ném exception tại đúng dòng gây ra mà phá vỡ synchronization ở bước sau.

### 13.3. Sai: dùng arrive khi thực sự cần wait

```java
writeMyPartialResult();
phaser.arrive();
readEverybodyResults(); // Có thể quá sớm.
```

Nếu `readEverybodyResults()` phụ thuộc mọi worker, code phải đợi pha tiến trước. Một arrival không đủ tạo happens-before ở phía consumer nếu consumer không chờ đúng barrier.

### 13.4. Sai: awaitAdvance nhưng không có arrival của party

```java
phaser.awaitAdvance(0);
```

Lời gọi này **không giảm unarrived count**. Nếu party này vốn có trách nhiệm arrival pha 0, mọi người có thể kẹt đợi nó. `awaitAdvance` thuần túy phù hợp với observer không cần arrival hoặc với party đã gọi `arrive`.

### 13.5. Sai: arrival sau deregister

Party đã gọi `arriveAndDeregister` không còn phải báo đến các pha mới. Nếu vẫn gọi arrival như một participant đang registered, dữ liệu đếm có thể sai; hãy register lại nếu logic thực sự cần tham gia một pha mới và phaser chưa terminated.

### 13.6. Sai: timeout xong thì deregister ngay trong pha đó

Khi một party đã `arrive()`, nhận timeout từ `awaitAdvanceInterruptibly` không reset lượt đến. Gọi `arriveAndDeregister` ngay có nguy cơ **double arrival**.

Chính sách khôi phục nên thuộc group coordinator, ví dụ `forceTermination` để báo batch abort và dọn các resources liên quan, hoặc đợi pha chuyển rồi deregister đúng pha mới.

### 13.7. Sai: không kiểm tra pha âm

Nếu Pharser đã terminated và `arriveAndAwaitAdvance` trả số âm, xử lý dữ liệu như thể nhóm đã hoàn tất bình thường là sai. Phải phân biệt thành công của một round và kết thúc/abort.

### 13.8. Sai: không có party đủ điều kiện chạy

Đăng ký 6 workers nhưng dùng executor fixed pool 2, rồi mỗi task blocking tại phase 0. Hai worker đầu có thể giữ hết pool threads, bốn worker còn lại nằm trong queue; `arriveAndAwaitAdvance` không tự làm các task còn lại được schedule. Thiết kế lại concurrency.

### 13.9. Sai: dùng metric snapshot để quyết định arrival

Một vòng `while(phaser.getUnarrivedParties() > 0)` không thay thế `awaitAdvance`. Snapshot không cung cấp blocking/wakeup protocol đúng và có thể gây spin CPU.

### 13.10. Sai: nhầm Phaser với đếm task hoàn tất một lần

Nếu chỉ cần thông báo “N task đã xong” một lần, `CountDownLatch` có thể đơn giản hơn. Phaser có lợi khi cần nhiều pha hoặc dynamic membership.

## 14. So sánh với CountDownLatch và CyclicBarrier

| Tiêu chí | `Phaser` | `CountDownLatch` | `CyclicBarrier` |
| --- | --- | --- | --- |
| Tái sử dụng nhiều vòng | **Có** | **Không**: latch không reset | **Có** |
| Số participant thay đổi | `register`/`arriveAndDeregister` | Đếm một lần cố định | Số parties cố định tại constructor |
| Ghi nhận đến mà không đợi | `arrive` | `countDown` | Không có arrival-only API riêng theo nghĩa này |
| Đến và chờ | `arriveAndAwaitAdvance` | `await` chờ latch, không phải arrival | `await` |
| Đợi pha bằng token | `awaitAdvance` | Không có phase | Dùng generation nội bộ |
| Timeout/interruption | `awaitAdvanceInterruptibly` | `await(timeout)` và interrupt | `await(timeout)` và interrupt |
| Lỗi timeout có phá barrier chung tự động? | **Không**: không tự đổi state Phaser | Count vẫn giữ | Có broken-barrier semantics |
| Rời các vòng sau | `arriveAndDeregister` | Không tương đương dynamic membership | Không có deregistration động chuẩn |

Phaser không mặc định “tốt hơn” hai lớp còn lại trong mọi tình huống. Nếu bạn chỉ có một lượt đồng bộ, dùng `CountDownLatch` dễ đọc. Nếu số parties cố định và mô hình là tất cả cùng `await`, `CyclicBarrier` có thể đơn giản. Dùng `Phaser` khi nhiều phase, dynamic parties hoặc cần tách arrival khỏi waiting.

## 15. Hiệu năng, quan sát và khả năng tiến triển

### 15.1. Barrier không làm task chạy song song hơn

Việc thêm `arriveAndAwaitAdvance` có thể giúp đồng bộ đúng nhưng cũng khiến worker nhanh phải đợi worker chậm. Tổng thời gian một pha gần như phụ thuộc **party chậm nhất** và chi phí scheduling/synchronization.

Không tối ưu bằng cách thay mọi `arriveAndAwaitAdvance` bằng `arrive` nếu bước tiếp theo **cần dữ liệu đã được đồng bộ**: nhanh nhưng sai kết quả không phải tăng tốc.

### 15.2. Số party lớn và tiering

`Phaser` có cơ chế **tiering** (cây parent/child phasers) để giảm tranh chấp khi số parties rất lớn. Đây là khả năng hiện hành của Java, không phải API đã deprecated. Tuy nhiên bài này tập trung vào `arrive` và `arriveAndAwaitAdvance`: trước khi dùng tiered phasers, cần nắm rõ thứ tự arrival và phase advancement trên một Phaser đơn giản.

### 15.3. Đo metric nhưng không dùng metric làm điều kiện đúng đắn

Các số `getArrivedParties`, `getUnarrivedParties`, `getRegisteredParties`, `getPhase` có thể in telemetry/debug, nhưng vì là snapshot nên dùng có trách nhiệm. Để có điểm đồng bộ đáng tin, dùng `arriveAndAwaitAdvance` hoặc `awaitAdvance(token)`, không poll snapshot liên tục.

### 15.4. Tránh “hàng rào quá dày”

Nếu đặt barrier sau từng phép tính cực nhỏ, phí scheduling và chờ các party chậm có thể lấn át lợi ích song song. Chọn độ hạt của mỗi phase đủ lớn, tách dữ liệu để giảm contention và đo wall-clock/throughput/p95 với workload thật.

## 16. Bài tập tự luyện có đáp án

### Bài 1 — Phân biệt arrive và arriveAndAwaitAdvance

Một party gọi `arrive()` khi party khác chưa đến. Caller có tiếp tục ngay không?

**Đáp án:** Có, sau khi ghi arrival (trừ các chi phí đặc biệt như callback chuyển pha nếu nó là party cuối); không đợi party khác. `arriveAndAwaitAdvance()` sẽ chờ pha tiến.

### Bài 2 — Tính unarrived

`Phaser p = new Phaser(3)`, chưa ai đến. Một party gọi `arrive()`. `getUnarrivedParties` bằng bao nhiêu nếu không có thao tác nào khác?

**Đáp án:** `2`, trong cùng pha 0. Registered vẫn 3.

### Bài 3 — Pha cũ và pha mới

Hai bên của `Phaser(2)` cùng hoàn tất pha 0. `arrive()` của party đầu báo số nào? Sau khi `arriveAndAwaitAdvance()` của party thứ hai trở về bình thường ở JDK 17, pha nào đã đạt được?

**Đáp án:** `arrive()` trả `0`, còn chờ chuyển pha đạt `1`; nếu Phaser terminated thì kiểm tra pha âm riêng.

### Bài 4 — Token tránh race

Vì sao `int p = phaser.arrive(); phaser.awaitAdvance(p);` an toàn hơn việc gọi `awaitAdvance(phaser.getPhase())` sau arrival?

**Đáp án:** Nếu phase đã tiến giữa hai lời gọi, `getPhase` có thể trả pha **mới** và khiến waiter chờ vòng tiếp theo. Token `p` chính là pha lượt đến đã áp dụng.

### Bài 5 — Caller đã arrive

Một worker đã gọi `arrive()` ở pha 0, nhưng pha 0 chưa tiến. Nó có thể gọi `arriveAndAwaitAdvance()` để chờ không?

**Đáp án:** Không, vì sẽ ghi nhận arrival **thứ hai** của cùng party trong pha đó. Dùng `awaitAdvance(token)` hoặc `awaitAdvanceInterruptibly`.

### Bài 6 — Chỉ chờ không đến

`Phaser(2)` có một party đã đến, party còn lại chỉ gọi `awaitAdvance(0)`. Pha có chuyển không?

**Đáp án:** Không vì vẫn thiếu một arrival. `awaitAdvance` không tự giảm unarrived count.

### Bài 7 — Ba party gồm main

Có hai worker và main cũng gọi `arriveAndAwaitAdvance` mỗi pha. Nên khởi tạo `new Phaser(2)` hay `new Phaser(3)`?

**Đáp án:** `new Phaser(3)` nếu đúng ba party này đều có trách nhiệm arrival. `2` chỉ đúng nếu main là observer không gọi arrival.

### Bài 8 — Arrive không deregister

Một party gọi `arrive()` rồi pha chuyển. Nó còn được tính vào registered ở pha sau không?

**Đáp án:** Có. Phải tiếp tục arrival ở pha tiếp theo hoặc dùng `arriveAndDeregister` vào thời điểm thích hợp.

### Bài 9 — Rời nhóm

Một worker hoàn tất công việc và sẽ không tham gia vòng sau. Phương thức nào phù hợp?

**Đáp án:** `arriveAndDeregister()`, vừa ghi arrival hiện tại vừa hủy đăng ký cho các pha sau, không chờ.

### Bài 10 — Timeout không rollback

Party gọi `arrive()` rồi `awaitAdvanceInterruptibly(p,100,MILLISECONDS)` timeout. Lượt đến cũ có bị xóa không?

**Đáp án:** Không. Arrival đã được ghi nhận; chờ timeout không tự thay đổi trạng thái Phaser.

### Bài 11 — Phục hồi lỗi

Một worker bị exception trước khi báo đến; các worker khác đang đợi ở barrier. Phương án nào giúp giải phóng hàng chờ khi muốn abort toàn batch?

**Đáp án:** Coordinator có thể gọi `forceTermination()` và các party phải xử lý pha âm/termination theo workflow; đồng thời dọn task/resource. Không có tác dụng rollback dữ liệu tự động.

### Bài 12 — Interruption

`arriveAndAwaitAdvance` có ném `InterruptedException` khi thread đợi bị interrupt không?

**Đáp án:** Không. Muốn interruptible waiting dùng `arrive()` kết hợp `awaitAdvanceInterruptibly`.

### Bài 13 — Party count và thread identity

Phaser có biết “thread A đã đăng ký” để cấm thread A arrive hai lần không?

**Đáp án:** Không. Phaser quản lý counts chứ không ghi ID mỗi party. Ứng dụng phải quản lý party identity ở tầng cao hơn.

### Bài 14 — Snapshot

`getUnarrivedParties()==1` có bảo đảm bạn luôn là party cuối nếu tiếp tục làm việc không?

**Đáp án:** Không. Threads khác có thể thay đổi trạng thái giữa lúc xem và lúc gọi arrival. Đây chỉ là snapshot quan sát.

### Bài 15 — Last party deregistration

`new Phaser(1)` và party gọi `arriveAndDeregister()`. Phaser mặc định có kết thúc không?

**Đáp án:** Có; registered trở về 0, `onAdvance` mặc định trả true và phaser terminated.

### Bài 16 — Pha âm

Một lời gọi `arriveAndAwaitAdvance()` trả số âm. Có thể dùng số đó làm index của vòng tính bình thường không?

**Đáp án:** Không. Đó là tín hiệu termination; phải dừng hoặc xử lý lỗi theo hợp đồng ứng dụng.

### Bài 17 — Executor thiếu worker

Có 10 parties nhưng executor fixed pool chỉ 2 worker, các task đầu tiên đều chờ barrier trước khi 8 task còn lại được chạy. Rủi ro?

**Đáp án:** Starvation/deadlock do thiếu threads để tất cả party đến. Tăng/điều phối concurrency phù hợp hoặc thiết kế stage không blocking như vậy; không trông chờ Phaser tự giải quyết.

### Bài 18 — Bộ nhớ và publication

Mỗi worker ghi vào ô riêng của mảng trước `arriveAndAwaitAdvance`; sau barrier đọc kết quả của mọi worker. Cơ chế nào hỗ trợ visibility?

**Đáp án:** Memory consistency/happens-before khi các actions trước arrival xảy ra trước phase advance và các actions sau advance. Vẫn cần tránh writes tranh chấp cùng một ô.

### Bài 19 — Chọn loại công cụ

Hệ thống chỉ cần biết khi năm task độc lập xong một lần rồi tiếp tục. Có nhất thiết chọn Phaser không?

**Đáp án:** Không. `CountDownLatch` thường đơn giản hơn cho synchronization một lần; Phaser hữu ích khi có nhiều pha hoặc dynamic parties.

### Bài 20 — Phương thức chờ theo pha

Một observer không đăng ký muốn biết khi pha 4 tiến lên. Có thể gọi `awaitAdvance(4)` mà không arrive không?

**Đáp án:** Có thể đợi như observer khi pha hiện tại đúng 4; lệnh không ghi arrival. Nhưng nếu phase đã khác 4 hoặc terminated, nó trả ngay; observer phải kiểm soát giả định về pha hiện tại và rollover.

### Bài 21 — Giảm độ hạt barrier

Mỗi phép cộng đơn lẻ đều có `arriveAndAwaitAdvance`, nhiều thread chờ nhau quá nhiều. Có cần dùng `arrive()` để “tăng tốc” bất kể correctness?

**Đáp án:** Không. Cần chọn stage đủ lớn, giảm số barrier khi giao thức cho phép, rồi đo. Thay bằng arrive mà bỏ chờ có thể làm sai thứ tự dữ liệu.

### Bài 22 — onAdvance

`onAdvance` được thực thi bởi ai, và có nên gọi lại `arrive` trên cùng Phaser từ bên trong callback đó không?

**Đáp án:** Nó chạy bởi party kích hoạt phase advance. Java không bảo đảm các thao tác registration/arrival/wait trên chính Phaser từ trong `onAdvance` có semantics xác định; tránh reentrant, giữ callback nhẹ.

## 17. Checklist áp dụng trong dự án

- [ ] Xác định số parties và ai sở hữu mỗi lượt arrival; **main có phải là party không?**
- [ ] Khởi tạo/register trước khi worker có thể arrive.
- [ ] Ghi `arrive` đúng **một lần mỗi party mỗi pha**.
- [ ] Chọn `arrive()` khi chỉ cần báo đến, **không cần đợi ngay**.
- [ ] Chọn `arriveAndAwaitAdvance()` nếu stage tiếp theo phải chờ đủ các bên.
- [ ] Nếu tách arrival và waiting, lưu **return token từ `arrive()`**.
- [ ] Không gọi `awaitAdvance(phaser.getPhase())` sau arrive khi có race chuyển pha.
- [ ] Không gọi `arriveAndAwaitAdvance` sau `arrive` của cùng party trong pha chưa tiến.
- [ ] Hiểu `awaitAdvance` **không ghi arrival**.
- [ ] Dùng `awaitAdvanceInterruptibly` khi cần timeout/interrupt; có failure policy rõ.
- [ ] Không coi timeout hoặc InterruptedException là đã rollback lượt arrival.
- [ ] Nếu task lỗi trước barrier, có cơ chế abort/forceTermination hoặc deregistration an toàn.
- [ ] Mọi caller kiểm tra termination/pha âm khi workflow có thể kết thúc.
- [ ] Khi rời các pha tiếp theo, dùng `arriveAndDeregister` **đúng một lượt**.
- [ ] Không sử dụng party identity ảo do Phaser không tự xác nhận thread đã đăng ký.
- [ ] Không dùng các getter state như một transaction/synchronization primitive.
- [ ] Đảm bảo executor có đủ khả năng chạy tất cả parties cần arrival.
- [ ] Đọc shared results chỉ khi hàng rào đã tiến theo protocol.
- [ ] Chọn `CountDownLatch`/`CyclicBarrier` nếu đơn giản hơn cho workload.
- [ ] Không dùng Phaser làm mutex bảo vệ writes tranh chấp trong một pha.
- [ ] Khi cần terminate nhiều pha, xem xét `onAdvance` và giới hạn callback.
- [ ] Test ít nhất hai pha để kiểm tra khả năng tái sử dụng.
- [ ] Test lỗi thiếu party, timeout, interrupt, termination và cleanup.
- [ ] Ghi rõ khác biệt `arrive` trả pha cũ với kết quả sau `arriveAndAwaitAdvance`.
- [ ] Chạy Java 17+ cho ví dụ, hiểu API lõi có từ Java 7 và vẫn hiện hành.

## 18. Tài liệu chính thức

- [Oracle Java SE 17 — Phaser](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Phaser.html): định nghĩa phase, `arrive`, `arriveAndAwaitAdvance`, `awaitAdvance`, registration/deregistration, termination, memory consistency và ví dụ sử dụng.
- [Oracle Java SE 17 — ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): submit, Future và shutdown lifecycle.
- [Oracle Java SE 17 — TimeUnit](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/TimeUnit.html): đơn vị thời gian cho chờ có deadline.
- [Oracle Java SE 17 — CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): lựa chọn đơn giản cho chờ một lần.
- [Oracle Java SE 17 — CyclicBarrier](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CyclicBarrier.html): barrier với số parties cố định.

## 19. Tổng kết

`arrive()` và `arriveAndAwaitAdvance()` đều **ghi nhận arrival của một party** vào Phaser, nhưng chỉ **`arriveAndAwaitAdvance()` đồng thời chờ các party còn lại để pha tiến lên**. Vì vậy:

- Dùng `arrive()` khi party cần báo đã xong stage hiện tại rồi tiếp tục được phần việc **độc lập**; khi cần barrier hãy `awaitAdvance(returnedPhase)`.
- Dùng `arriveAndAwaitAdvance()` khi tất cả parties cần gặp nhau tại cuối một stage để công bố kết quả và bắt đầu stage mới.
- Khi cần timeout hay interruptible wait, tách `arrive()` với `awaitAdvanceInterruptibly`; đừng giả định timeout sẽ undo arrival.
- Khi không còn tham gia, chọn `arriveAndDeregister()` đúng pha; khi batch phải abort, coordinator có thể dùng `forceTermination()` theo contract.
- Đăng ký đúng số parties, không arrival hai lần, không bỏ sót worker, không dùng snapshot làm điều kiện barrier và luôn phân biệt số pha âm khi terminated.

**`Phaser` vẫn là một công cụ đồng bộ hữu ích trong Java hiện đại** cho nhiều vòng với số parties linh hoạt. Cách dùng đúng bắt đầu bằng hiểu rõ hai hành động **“đến”** và **“đến rồi chờ”**, chứ không chỉ thuộc tên phương thức.