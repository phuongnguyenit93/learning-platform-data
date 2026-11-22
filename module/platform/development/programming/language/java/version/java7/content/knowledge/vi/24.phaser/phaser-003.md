# Java 7 — Phaser: Đăng ký linh hoạt bằng register, bulkRegister

## 1. Tại sao Phaser cần đăng ký linh hoạt?

Một bài toán xử lý song song thường có các giai đoạn (*phases*): chuẩn bị dữ liệu, tính toán, tổng hợp, chuyển kết quả. Trước khi chuyển sang giai đoạn sau, một nhóm công việc phải báo **đã đến điểm đồng bộ**. Khi số người tham gia cố định, `CountDownLatch` hoặc `CyclicBarrier` có thể đáp ứng một số nhu cầu. Nhưng nếu số task có thể **tăng/giảm khi ứng dụng đang chạy**, `java.util.concurrent.Phaser` cung cấp mô hình linh hoạt hơn.

Hai phương thức chính:

- `register()`: đăng ký **thêm một party chưa đến** (*unarrived party*) với phaser.
- `bulkRegister(int parties)`: đăng ký **cùng lúc nhiều party chưa đến**, tiết kiệm các lời gọi register lặp và giúp khởi tạo một lô công việc có cấu trúc rõ ràng.

Phương thức tương ứng khi party hoàn tất và không tham gia các giai đoạn tiếp theo là `arriveAndDeregister()`: **vừa báo đến phase hiện tại, vừa giảm số parties đăng ký cho các phase sau**.

Bài này giải thích chính xác cách đăng ký, khi nào registration có hiệu lực, số đếm parties/unarrived, xử lý kết quả trả về, đăng ký khi phase đã hoạt động, rủi ro race với submit task, vòng đời termination, sai lầm khi lạm dụng arrival và các ví dụ Java 17+ chạy được. API `Phaser` có từ Java 7 và **vẫn hiện hành trên Java SE 17+**.

## 2. Từ vựng cốt lõi: party, phase, arrival

**Party** là một **nghĩa vụ tham gia đồng bộ** được tính trong phaser. Một party **không phải một thread ID** được Java tự lưu. Phương thức `register()` chỉ tăng counters; Java **không tạo một thread**, không lưu danh sách thread đã đăng ký và không bảo đảm chính thread gọi register sẽ là thread gọi arrive.

**Phase** là vòng đồng bộ, bắt đầu tại số **0**. Khi tất cả parties đang được tính cho phase đó đã báo đến, phaser **advance** sang phase kế tiếp. Phase có thể tiếp tục lặp cho nhiều giai đoạn.

**Arrival** là hành động party thông báo đã xong phần việc của phase hiện tại. Party có thể chọn:

- `arrive()` — đến mà **không đợi** và **vẫn đăng ký** cho phase sau.
- `arriveAndAwaitAdvance()` — đến và **chờ phase tiến**.
- `arriveAndDeregister()` — đến, đồng thời **rời nhóm đăng ký**.

Những lời gọi này không tương đương với `register()`: **register tạo thêm nghĩa vụ phải đến**, còn arrive hoàn thành một nghĩa vụ ở phase hiện tại.

### 2.1. Ba counters quan trọng

| Phương thức | Ý nghĩa |
| --- | --- |
| `getRegisteredParties()` | Tổng số parties hiện đăng ký |
| `getUnarrivedParties()` | Số parties còn **chưa** báo đến phase hiện tại |
| `getArrivedParties()` | Số parties đã báo đến phase hiện tại |
| `getPhase()` | Phase hiện tại; giá trị âm nếu phaser đã terminated |
| `isTerminated()` | Phaser đã vào trạng thái chấm dứt hay chưa |

Trước khi có hoạt động đồng thời, khi phaser active bình thường:

```text
registered parties = arrived parties + unarrived parties
```

Nhưng các getter là **các snapshot quan sát**, có thể thay đổi ngay lập tức do thread khác register/arrive/deregister. Đừng dùng nhiều lần đọc riêng rồi coi chúng là một atomic snapshot, và **không lấy getUnarrivedParties() làm cơ chế thay cho việc đến barrier đúng cách**.

### 2.2. Sơ đồ một phase

```text
Phaser phase 0, parties=3, unarrived=3

Party A arrive() --------------> unarrived=2
Party B arrive() --------------> unarrived=1
Party C arrive() --------------> unarrived=0
                                         |
                                         v
                                  ADVANCE 0 -> 1
                                         |
                           phase 1, unarrived=3
```

Nếu ở phase 0 một party gọi `arriveAndDeregister()`, tổng số parties của phase mới sẽ **nhỏ hơn**, vì party đó không tiếp tục tham gia. Nếu ngay giữa phase 0 có task đăng ký mới, số unarrived của phase hiện tại có thể **tăng**. Đây là điểm khác biệt quan trọng nhất so với barrier có số participants cố định.

## 3. API registration và kết quả trả về

Các signatures:

```java
public int register();
public int bulkRegister(int parties);
```

Đây là **chữ ký API**, không phải đoạn chương trình độc lập.

| Lệnh | Tác dụng khi phaser active | Return value | Lưu ý |
| --- | --- | --- | --- |
| `register()` | Thêm 1 registered, 1 unarrived | Phase được áp dụng registration | Có thể chờ một `onAdvance` đang thực hiện |
| `bulkRegister(n)`, n dương | Thêm n registered, n unarrived | Phase được áp dụng registration | n là số parties **bổ sung**, không phải tổng |
| `bulkRegister(0)` | Không thay đổi số parties | Phase hiện tại | Hữu ích kiểm tra edge case, không tạo party |
| `bulkRegister(n)`, n âm | Không hợp lệ | Ném `IllegalArgumentException` | Validate count trước |
| Register trên phaser terminated | **Không** thêm party | Số phase âm | Không được coi là đăng ký thành công |
| Vượt maximum parties được hỗ trợ | Không thể thêm số lượng đó | Ném `IllegalStateException` | Đây là giới hạn hữu hạn của implementation/API |

**Chú ý:** `register()` và `bulkRegister(...)` **không trả ID cho party**. Giá trị kiểu `int` chúng trả là **số phase mà đăng ký đã áp dụng**, không phải số parties hiện tại và cũng không phải mã thành công 0/1 chung.

### 3.1. Ví dụ ngay sau khởi tạo

```java
Phaser phaser = new Phaser(1);  // Một party: controller.
int p1 = phaser.register();      // Thêm một party.
int p2 = phaser.bulkRegister(3); // Thêm ba parties.
int count = phaser.getRegisteredParties(); // 5 nếu chưa có concurrent mutation.
```

Đây là snippet đặt trong một phương thức Java với `import java.util.concurrent.Phaser;`. `p1`, `p2` đều là phase đăng ký áp dụng; nếu không có ai tiến phase, chúng bằng **0**. Không diễn giải `bulkRegister(3)` là “chuyển tổng parties thành 3” — nó **cộng thêm ba**.

### 3.2. Vì sao phải kiểm tra giá trị âm?

Phaser có thể đã terminated do tất cả parties rời đi, do `onAdvance(...)` trả true, hoặc do `forceTermination()`. Lúc này:

```java
int phase = phaser.register();
if (phase < 0) {
    throw new IllegalStateException("Phaser đã terminated");
}
```

Đây là snippet trong phương thức với `Phaser phaser` đã tồn tại. Đối với `bulkRegister(n)` cũng kiểm tra tương tự. Bỏ qua giá trị âm rồi khởi tạo worker và gọi `arriveAndAwaitAdvance()` có thể làm logic “đã tham gia” sai: **registration không thực sự diễn ra**.

### 3.3. bulkRegister(0) không có nghĩa giải phóng ai

`phaser.bulkRegister(0)` là phép **không thêm party**. Nó không gọi arrive, không deregister, không tự advance và không làm các threads đang đợi được giải phóng. Đừng dùng nó để thay việc báo hoàn thành.

## 4. Khởi tạo parties bằng constructor hay đăng ký sau?

`Phaser` cung cấp:

```java
Phaser empty = new Phaser();  // 0 parties, phase 0.
Phaser three = new Phaser(3); // 3 parties đã đăng ký, đều unarrived.
```

Hai dòng độc lập này hợp lệ trong phương thức Java 17+. Chúng có ý nghĩa gần với việc đăng ký trước, nhưng cấu trúc vòng đời khác:

- `new Phaser()`: khởi đầu **không có party**, vẫn chưa terminated; phải đăng ký participants khi cần.
- `new Phaser(3)`: ngay từ đầu đã có ba nghĩa vụ phải đến ở phase 0.
- `new Phaser(1)`: thường dùng khi **controller/main thread cũng tham gia barrier**; controller có trách nhiệm gọi arrive mỗi phase hoặc deregister.
- `new Phaser(0)` cũng tạo phaser active rỗng; đừng nghĩ nó tự terminated ngay khi vừa khởi tạo.

### 4.1. Khi nào dùng constructor count?

Dùng khi biết chắc số parties ban đầu, đặc biệt nếu tất cả workers được tạo/đăng ký ngay. Ví dụ có 4 workers cố định, dùng `new Phaser(4)` và mỗi worker có một arrival mỗi phase.

Nhưng nếu controller cũng tham gia, phải tính **+1**. Với bốn workers + controller là **5 parties**, không phải 4.

### 4.2. Khi nào dùng register()?

Khi task được thêm từng cái, ví dụ một worker mới nhận trách nhiệm hoàn thành các phase tương lai:

```java
int joinedPhase = phaser.register();
if (joinedPhase < 0) {
    // Không submit task vì registration không thành công.
}
```

Nó thuận tiện trong code theo kiểu một task tự đăng ký, nhưng phải đảm bảo task **được submit/chạy được hoặc có cleanup** sau registration. Nếu submit bị từ chối và party còn đăng ký nhưng không arrive, barrier có thể treo.

### 4.3. Khi nào dùng bulkRegister(n)?

Khi đã có một **lô n tasks** cùng chịu trách nhiệm tham gia, đặc biệt trước khi submit qua ExecutorService:

```java
Phaser phaser = new Phaser(1);  // Controller.
int registeredAt = phaser.bulkRegister(tasks.size());
if (registeredAt < 0) {
    throw new IllegalStateException("Không thể đăng ký lô");
}
```

Đây là snippet trong phương thức với `List<?> tasks` đã xác định. Sau đó mới submit các tasks tương ứng; mọi task phải hoàn thành đúng số lần arrival và rời nhóm khi vòng đời kết thúc.

Điểm tốt của bulk registration: **cập nhật một lô trong một lời gọi** thay vì nhiều lời gọi `register()`, dễ đảm bảo “đã đăng ký đủ tất cả workers trước khi controller bắt đầu chờ”. Nhưng nó **không tự tạo/submit các task**, và không tự phát hành token định danh cho từng party.

## 5. Registration trong phase đang hoạt động

Phaser khác CyclicBarrier ở chỗ số parties có thể đổi **giữa các phase**, thậm chí **trong lúc một phase đang chờ các arrivals cuối**.

Giả sử:

```text
phase 0: parties=2, unarrived=2
A đã arrive(): parties=2, unarrived=1
C register(): parties=3, unarrived=2  <-- thêm nghĩa vụ cho phase 0
C arriveAndDeregister(): parties=2, unarrived=1
Controller arriveAndAwaitAdvance():
    unarrived về 0 -> phase tiến sang 1
```

Nếu C không arrive/deregister ở phase 0, controller vẫn phải chờ C. **Đăng ký muộn có thể trì hoãn barrier hiện tại.** Khi ứng dụng đang chạy đa thread, thời điểm registration được áp dụng có thể phụ thuộc cạnh tranh với phase advance; dùng **phase number trả về** để biết registration thuộc phase nào. Không đoán bằng `getPhase()` đọc trước đó rồi coi như atomic với lời gọi register.

### 5.1. register() trong lúc onAdvance đang chạy

Javadoc Java SE 17 cho biết nếu `onAdvance(int,int)` đang được gọi, `register()` và `bulkRegister()` **có thể phải đợi callback onAdvance hoàn thành** trước khi trả về. Vì thế không được quảng bá register là “không bao giờ block”.

Hệ quả: `onAdvance` nên **ngắn gọn, không I/O chặn dài, không gọi ngược register/arrival/waiting methods của cùng phaser**. Javadoc nói tác dụng của registration/arrival/waiting bên trong `onAdvance` là không được đặc tả.

### 5.2. Race cần tránh: xem phase rồi mới đăng ký

Sai về mặt điều phối nếu code giả định:

```java
int observed = phaser.getPhase();
// Thread khác có thể hoàn tất barrier ở đây!
int registrationPhase = phaser.register();
// registrationPhase có thể khác observed.
```

Đây là snippet minh họa, không phải một bug xảy ra mọi lần. Điều đúng là **dùng registrationPhase** làm phase registration được áp dụng. Nếu nghiệp vụ bắt buộc một task thuộc đúng một wave/phase xác định, phải có **protocol cấp ứng dụng** để đóng việc nhận participants cho wave đó trước khi đẩy barrier đi tiếp.

### 5.3. Không có hàm deregister riêng không đi kèm arrival

API chuẩn có `arriveAndDeregister()`, nghĩa là rời đi **cùng lúc báo đến current phase**. Nếu vừa register xong nhưng task không bao giờ được submit, controller phải điều phối **một lần arriveAndDeregister tương ứng** hoặc force termination theo failure policy, không “trừ bớt bằng getRegisteredParties()”.

## 6. Ba kiểu arrival và waiting phải phân biệt

| API | Đánh dấu arrival? | Chờ phase tiến? | Giữ party cho phase kế? |
| --- | --- | --- | --- |
| `arrive()` | Có | Không | Có |
| `arriveAndAwaitAdvance()` | Có | Có | Có |
| `arriveAndDeregister()` | Có | Không | **Không** |
| `awaitAdvance(phase)` | **Không** | Có, nếu vẫn ở phase được truyền | Không thay số parties |
| `awaitAdvanceInterruptibly(phase)` | **Không** | Có, interruptible | Không thay số parties |
| `awaitAdvanceInterruptibly(phase,timeout,unit)` | **Không** | Có giới hạn timeout | Không thay số parties |

### 6.1. Một party đến mà không chờ

```java
int arrivalPhase = phaser.arrive();
doOtherIndependentWork();
int nextPhase = phaser.awaitAdvance(arrivalPhase);
```

Đây là snippet trong phương thức với `Phaser phaser`, `doOtherIndependentWork()` là hàm nghiệp vụ minh họa. Phải đảm bảo party **chỉ arrive đúng một lần ở phase đó**. Một thread muốn tách phần “arrive” và phần “wait” thì `awaitAdvance(arrivalPhase)` là cách chuẩn: **awaitAdvance không tự arrive**.

### 6.2. Đến và chờ trong một lời gọi

```java
int nextPhase = phaser.arriveAndAwaitAdvance();
if (nextPhase < 0) {
    // Phaser đã terminated; xử lý shutdown/failure.
}
```

Đây là snippet trong phương thức. Phương thức đợi đến khi mọi registered parties arrive (hoặc phaser terminated), nên nó **có thể chặn thread**. Khi phase advance bình thường, trả số phase mới. Nếu terminated, trả giá trị âm.

### 6.3. Rời nhóm tại điểm đến

```java
int phaseOfDeparture = phaser.arriveAndDeregister();
```

Nó làm giảm **registered** và **unarrived** phù hợp với phase hiện tại, và không chờ. Thích hợp trong `finally` của worker khi chắc chắn worker còn sở hữu một registration chưa bị deregister.

**Quan trọng:** không gọi `arriveAndDeregister()` **thêm lần nữa** trên behalf của cùng một party nếu đã deregister từ trước. Phaser không kiểm tra danh tính, nên có thể âm thầm làm lệch counter hoặc ném IllegalStateException ở thao tác sau.

### 6.4. awaitAdvance không cần caller đăng ký

Một thread có thể chỉ **quan sát phase** mà không phải registered party, rồi `awaitAdvance(phase)`. Nó sẽ đợi phase thay đổi, nhưng **không làm giảm số unarrived**. Vì vậy đừng viết main là observer nhưng lại tính nó vào số party workers, hoặc ngược lại quên controller đã được register.

### 6.5. Interruptible và timeout không xóa registration

`awaitAdvanceInterruptibly(...)` có thể ném `InterruptedException` hoặc `TimeoutException`. **Phaser không tự thay đổi trạng thái arrivals/registrations** chỉ vì một thread bỏ chờ. Nếu party đã `arrive()` trước đó, đừng arrive lần thứ hai. Nếu worker chưa arrive khi timeout, bạn phải xử lý nghĩa vụ đó rõ ràng (arrive/deregister một lần khi hợp lệ hoặc `forceTermination()` để giải phóng toàn hệ thống). Không nuốt timeout rồi bỏ mặc registered party.

## 7. Chương trình Java 17+ hoàn chỉnh: register, bulkRegister và counters

**Tệp: `RegistrationStateDemo.java`**

Đây là một demo **một thread** mô phỏng bốn **logical parties** (controller, A, B, C). Mục tiêu là nhìn thấy số đếm thay đổi theo từng API mà không có nondeterminism do scheduler. Việc cùng một thread gọi `arrive` thay các logical parties trong demo minh họa rõ rằng Phaser **không lưu thread identity cho từng party**; trong ứng dụng thật mỗi task/owner phải chịu đúng nghĩa vụ riêng của mình.

```java
import java.util.concurrent.Phaser;

public class RegistrationStateDemo {
    private static void state(String label, Phaser p) {
        System.out.println(label + ": phase=" + p.getPhase()
                + ", parties=" + p.getRegisteredParties()
                + ", unarrived=" + p.getUnarrivedParties());
    }

    public static void main(String[] args) {
        Phaser p = new Phaser(1); // Controller is one logical party.
        state("initial", p);
        System.out.println("bulkRegister(0) = " + p.bulkRegister(0));
        System.out.println("register phase = " + p.register());
        System.out.println("bulkRegister(2) phase = " + p.bulkRegister(2));
        state("after registering", p);

        p.arrive(); // Logical party A arrives but stays registered.
        state("A arrived", p);
        p.arriveAndDeregister(); // Logical party B leaves.
        state("B left", p);
        p.arriveAndDeregister(); // Logical party C leaves.
        state("C left", p);

        int advanced = p.arriveAndAwaitAdvance(); // Controller completes phase 0.
        System.out.println("controller advanced to = " + advanced);
        state("after barrier", p);

        p.arriveAndDeregister(); // A leaves phase 1.
        p.arriveAndDeregister(); // Controller leaves phase 1.
        System.out.println("terminated = " + p.isTerminated());
        System.out.println("remaining parties = " + p.getRegisteredParties());
        System.out.println("register after termination negative = " + (p.register() < 0));
        System.out.println("bulk after termination negative = " + (p.bulkRegister(2) < 0));
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 RegistrationStateDemo.java
java RegistrationStateDemo
```

**Stdout đã kiểm thử trên Windows/JDK 24, tương thích Java 17+:**

```text
initial: phase=0, parties=1, unarrived=1
bulkRegister(0) = 0
register phase = 0
bulkRegister(2) phase = 0
after registering: phase=0, parties=4, unarrived=4
A arrived: phase=0, parties=4, unarrived=3
B left: phase=0, parties=3, unarrived=2
C left: phase=0, parties=2, unarrived=1
controller advanced to = 1
after barrier: phase=1, parties=2, unarrived=2
terminated = true
remaining parties = 0
register after termination negative = true
bulk after termination negative = true
```

### 7.1. Phân tích counters

| Thao tác | Phase | Registered | Unarrived |
| --- | ---: | ---: | ---: |
| `new Phaser(1)` | 0 | 1 | 1 |
| `bulkRegister(0)` | 0 | 1 | 1 |
| `register()` | 0 | 2 | 2 |
| `bulkRegister(2)` | 0 | 4 | 4 |
| A `arrive()` | 0 | 4 | 3 |
| B `arriveAndDeregister()` | 0 | 3 | 2 |
| C `arriveAndDeregister()` | 0 | 2 | 1 |
| Controller `arriveAndAwaitAdvance()` | 1 | 2 | 2 |
| A và controller lần lượt deregister | Terminated | 0 | Không sử dụng làm đồng bộ |

Điểm then chốt: **register tăng hai counters** (registered và unarrived), còn **deregister khi đến giảm hai counters**. `arrive()` chỉ làm giảm unarrived nhưng không giảm registered, vì party đó vẫn tham gia phase sau.

### 7.2. Vì sao phaser terminated sau khi tất cả rời đi?

Trong `Phaser` mặc định, `onAdvance(phase,registeredParties)` trả true khi một lần deregistration khiến registered parties về 0. Lúc đó phaser terminated. Sau termination, `register()`/`bulkRegister(2)` trả **negative phase**, không hồi sinh barrier.

### 7.3. Vì sao số phase trong output là 0 rồi 1?

Phaser bắt đầu tại phase 0. A, B và C đã hoàn thành nghĩa vụ phase 0; controller là party cuối cùng đến nên phase tiến 1. Vì A vẫn còn đăng ký sau `arrive()`, phase 1 có hai parties (A và controller). Chỉ khi cả hai gọi `arriveAndDeregister()`, total về 0 và mặc định terminate.

## 8. Chương trình Java 17+ hoàn chỉnh: đăng ký muộn giữa phase

**Tệp: `LateRegistrationDemo.java`**

Demo vẫn dùng một thread để điều khiển **ba logical parties**, có thể xác định chính xác thời điểm đăng ký muộn. Sau khi A đã arrive ở phase 0, controller chưa arrive; C mới register. Phaser tăng **unarrived từ 1 lên 2**, cho thấy một party đăng ký muộn **có thể làm thay đổi barrier hiện tại**.

```java
import java.util.concurrent.Phaser;

public class LateRegistrationDemo {
    public static void main(String[] args) {
        Phaser phaser = new Phaser(2); // Two logical parties: controller and A.
        phaser.arrive(); // A arrives at phase 0; controller has not arrived.
        System.out.println("unarrived before late registration = " +
                phaser.getUnarrivedParties());

        int joinedAt = phaser.register(); // C joins the current phase.
        System.out.println("late registration phase = " + joinedAt);
        System.out.println("unarrived after late registration = " +
                phaser.getUnarrivedParties());

        phaser.arriveAndDeregister(); // C arrives and leaves.
        System.out.println("phase before controller arrival = " + phaser.getPhase());

        int next = phaser.arriveAndAwaitAdvance(); // Controller advances the phase.
        System.out.println("phase after controller arrival = " + next);

        phaser.arriveAndDeregister(); // A leaves phase 1.
        phaser.arriveAndDeregister(); // Controller leaves; zero parties.
        System.out.println("terminated = " + phaser.isTerminated());
    }
}
```

Lệnh:

```bash
javac --release 17 LateRegistrationDemo.java
java LateRegistrationDemo
```

**Stdout đã kiểm thử trên Windows/JDK 24:**

```text
unarrived before late registration = 1
late registration phase = 0
unarrived after late registration = 2
phase before controller arrival = 0
phase after controller arrival = 1
terminated = true
```

### 8.1. Bài học từ registration muộn

Trong hệ thống thật, thread A, controller và C có thể chạy đồng thời. Một thời điểm `register` có thể cạnh tranh với final arrival. **Không suy phase áp dụng registration từ tên task hay số phase từng đọc trước đó.** Dùng **return value của `register()`** và một quy tắc admission/owner phù hợp nếu business cần xác định chính xác task nào thuộc batch nào.

Nếu không muốn C tham gia phase 0, application phải **khóa việc đăng ký của phase 0 trước final arrival** rồi đăng ký C cho phase kế tiếp theo giao thức có đồng bộ. Phaser tự nó **không cung cấp API “register trực tiếp cho phase số N trong tương lai”**.

## 9. Chương trình Java 17+ hoàn chỉnh: bulkRegister trước khi chạy nhiều workers

**Tệp: `BatchWorkersDemo.java`**

Đây là ví dụ **đa luồng thực**, không chỉ tăng đếm trong một thread. Một controller đăng ký sẵn **3 worker parties bằng `bulkRegister(3)`**, submit ba workers vào ExecutorService có ba threads, và cùng chúng phối hợp qua **2 stages**.

Các workers thực hiện:

1. Tăng counter của stage mình vừa xử lý.
2. Gọi `arriveAndAwaitAdvance()` để đợi cả ba workers **và controller** tới barrier.
3. Làm stage tiếp theo.
4. Cuối cùng gọi `arriveAndDeregister()` đúng một lần.

Controller cũng đến barrier của mỗi stage, kiểm tra số workers đã hoàn thành stage sau khi advance. Mọi output được in ở main sau đồng bộ nên **không phụ thuộc thứ tự chạy từng worker**.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.Phaser;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicIntegerArray;

public class BatchWorkersDemo {
    private static final int WORKERS = 3;
    private static final int STAGES = 2;

    public static void main(String[] args) throws Exception {
        Phaser p = new Phaser(1); // Controller is registered.
        int phaseAtRegistration = p.bulkRegister(WORKERS);
        System.out.println("registration phase = " + phaseAtRegistration);
        System.out.println("registered parties = " + p.getRegisteredParties());

        AtomicIntegerArray completed = new AtomicIntegerArray(STAGES);
        ExecutorService workers = Executors.newFixedThreadPool(WORKERS);
        List<Future<?>> jobs = new ArrayList<>();
        try {
            for (int worker = 0; worker < WORKERS; worker++) {
                jobs.add(workers.submit(() -> {
                    try {
                        for (int stage = 0; stage < STAGES; stage++) {
                            completed.incrementAndGet(stage);
                            int phase = p.arriveAndAwaitAdvance();
                            if (phase < 0) {
                                throw new IllegalStateException("Phaser terminated");
                            }
                        }
                    } catch (RuntimeException | Error failure) {
                        p.forceTermination();
                        throw failure;
                    } finally {
                        p.arriveAndDeregister();
                    }
                }));
            }

            for (int stage = 0; stage < STAGES; stage++) {
                int nextPhase = p.arriveAndAwaitAdvance();
                if (nextPhase < 0) {
                    throw new IllegalStateException("Phaser terminated");
                }
                System.out.println("completed stage " + stage + " = " +
                        completed.get(stage));
                System.out.println("advanced to phase = " + nextPhase);
            }
            for (Future<?> job : jobs) {
                job.get(5, TimeUnit.SECONDS);
            }
        } catch (Exception error) {
            p.forceTermination();
            throw error;
        } finally {
            p.arriveAndDeregister(); // Controller leaves.
            workers.shutdownNow();
            workers.awaitTermination(5, TimeUnit.SECONDS);
        }

        System.out.println("all workers finished = " +
                jobs.stream().allMatch(Future::isDone));
        System.out.println("registered after exit = " + p.getRegisteredParties());
        System.out.println("terminated = " + p.isTerminated());
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 BatchWorkersDemo.java
java BatchWorkersDemo
```

**Stdout đã kiểm thử với Windows/JDK 24; mã tương thích Java 17:**

```text
registration phase = 0
registered parties = 4
completed stage 0 = 3
advanced to phase = 1
completed stage 1 = 3
advanced to phase = 2
all workers finished = true
registered after exit = 0
terminated = true
```

### 9.1. Tại sao đăng ký đủ parties trước submit?

Nếu submit workers rồi mới bắt đầu từng lượt `register()`, một worker chạy nhanh có thể `arriveAndAwaitAdvance()` trước khi các workers khác kịp đăng ký. Barrier có thể tiến quá sớm, còn worker chậm vô tình tham gia phase sau. `bulkRegister(WORKERS)` **trước khi submit** xác lập ngay nghĩa vụ của cả nhóm cho phase đầu.

### 9.2. Vì sao registered parties bằng 4?

Controller được tính ngay từ `new Phaser(1)`; ba workers được thêm bằng bulkRegister(3). Tổng là 4. Mỗi phase chỉ tiến khi cả ba workers **và controller** arrive.

### 9.3. Vì sao counter AtomicIntegerArray?

Ba threads cùng cập nhật counter stage. Dùng `AtomicIntegerArray` tránh data race. Sau `arriveAndAwaitAdvance()` của controller trả về, tất cả parties đã gọi arrive ở stage đó. Phép tăng counter diễn ra **trước arrive**, nên đọc kết quả sau advance là an toàn theo memory consistency effects của Phaser.

### 9.4. Vì sao mỗi worker finally deregister?

Workers tham gia cả hai stages rồi rời đi. Controller cũng deregister ở finally. Khi tất cả đã rời, registered count thành 0 và phaser mặc định terminated.

Cần nhớ: `finally` chỉ đúng nếu mỗi worker đã được bulk-register **đúng một slot**, và worker chưa deregister ở nơi khác. Với workflow phức tạp, giữ một lifecycle flag/owner để không double-deregister.

### 9.5. Vì sao có forceTermination khi thất bại?

Nếu một worker ném RuntimeException trong lúc những workers khác đang đợi barrier, chúng có thể đợi mãi. `p.forceTermination()` làm phaser terminated và giải phóng những waits, cho phép các threads thấy kết quả âm, fail request và cleanup.

Ví dụ không cố demo các lỗi ngẫu nhiên nên stdout vẫn xác định. Production cần kết hợp forceTermination với logging, propagation của nguyên nhân lỗi, timeout và chính sách cancel; đừng coi forceTermination là rollback của công việc đã làm.

### 9.6. Vì sao cần worker pool có đủ threads?

Nếu đã đăng ký ba workers, nhưng executor chỉ có một thread mà worker đầu gọi `arriveAndAwaitAdvance()` ngay, hai workers còn lại có thể vẫn nằm trong queue và không bao giờ chạy để tới barrier. **Thread starvation/deadlock** là rủi ro rõ ràng. Ví dụ dùng đúng ba worker threads để mọi worker có thể tiến tới barrier.

Trong production có thể dùng thiết kế khác như ForkJoinPool/virtual threads (Java 21+) nếu phù hợp, nhưng phải phân tích **tổng số blocking participants** và capacity. Không mặc định rằng một pool nhỏ có thể chạy tuần tự mọi task nếu từng task lại chờ những task còn nằm trong queue.

## 10. Phân biệt register với arriveAndDeregister trong workflow thực

### 10.1. Register trước khi submit work

Một pattern quản lý lô:

```text
Controller
    |
    +-- register controller: new Phaser(1)
    |
    +-- bulkRegister(N) --------------> N nghĩa vụ chưa đến
    |
    +-- submit N jobs
    |          |
    |          +-- job 1 stage 0 --> arriveAndAwaitAdvance()
    |          +-- job 2 stage 0 --> arriveAndAwaitAdvance()
    |          +-- ...
    |
    +-- controller stage 0 ----------> arriveAndAwaitAdvance()
                                       |
                                       v
                                    phase 1
                                       |
                                stage tiếp theo
                                       |
                                    cleanup
                                       |
                               arriveAndDeregister()
```

Điểm cần quản lý cẩn thận: nếu chỉ submit thành công **K nhỏ hơn N** jobs, thì N-K slots chưa bao giờ có worker thực hiện arrival. Phải xử lý bằng policy rõ: **deregister các slots chưa cấp cho task thực**, hoặc force terminate toàn đợt. Không bỏ mặc barrier.

### 10.2. Worker tự register

Một worker có thể tự gọi `register()`, nhưng nếu controller đang ở barrier, có race giữa registration của worker muộn và phase advance. Điều phối bằng một launch gate/admission lock hoặc controller bulk-register trước thường dễ chứng minh tính đúng hơn.

### 10.3. Dynamic addition giữa các stages

Một service có thể quyết định thêm worker mới để tham gia **các phase kế tiếp**. Nếu muốn chính xác, phải xác lập khi nào nhận thêm worker: ví dụ controller dừng nhận registration, chờ wave cũ xong, rồi mở wave mới và register trước khi cho các parties của wave mới bắt đầu.

**Không có nghĩa** `register()` sẽ tự hiểu “worker này tham gia phase sau” nếu gọi giữa phase hiện tại; nó áp dụng vào phase mà chính hàm trả về.

### 10.4. Dynamic removal

Worker có thể bỏ tham gia bằng `arriveAndDeregister()` khi hoàn tất một phase hoặc không cần xử lý các phase sau. Nếu worker bị hủy trước khi đến phase, owner cần bảo đảm một lần arrival/deregistration thích hợp hoặc force termination. Không có API “giảm registered count bằng setCount()”.

## 11. Điều gì xảy ra khi phaser không còn parties?

### 11.1. Mặc định terminate khi số parties về 0

`Phaser` có `onAdvance(int phase, int registeredParties)` được gọi khi một phase sắp tiến. Mặc định nó trả `true` nếu registration count thành **0 do deregistration**. Vì vậy một phaser có workers rời hết thường chuyển sang **terminated**.

Khi terminated:

- `isTerminated() == true`.
- `getPhase()` trả một giá trị **âm**.
- `register()` và `bulkRegister(n)` không thêm parties; trả giá trị âm.
- Các phương thức chờ trả về ngay theo termination semantics.
- Không thể dùng `register()` để “khôi phục” phaser đã terminated; muốn một lượt công việc độc lập mới, thường tạo Phaser mới.

### 11.2. Initial zero parties không phải terminated

`new Phaser()` ban đầu có 0 parties **nhưng active**. Có thể register worker đầu tiên sau đó. Khác với **trở về 0 parties qua deregistration** ở implementation mặc định, sẽ kích hoạt termination.

### 11.3. forceTermination()

`phaser.forceTermination()` buộc phaser vào trạng thái terminated để các threads đang đợi không tiếp tục mắc kẹt. Nó phù hợp khi hủy toàn bộ batch do lỗi, deadline hoặc shutdown. Nó **không** tự interrupt/cancel mọi worker, không rollback database/file writes và không hủy những Futures ứng dụng đã submit.

Sau force termination, party owner vẫn phải dọn tài nguyên, báo lỗi, stop workers và kiểm soát submit mới. Không coi một phase âm là “batch hoàn thành thành công”.

### 11.4. Override onAdvance để có chính sách lifecycle riêng

Ví dụ minh họa (không phải chương trình độc lập):

```java
Phaser reusable = new Phaser() {
    @Override
    protected boolean onAdvance(int phase, int registeredParties) {
        return false; // Không terminate chỉ vì 0 parties.
    }
};
```

Khi muốn phaser tiếp tục active cả lúc không có party, có thể override như trên. Tuy nhiên nếu registered count về 0, bạn vẫn cần protocol để register parties mới; không có nghĩa phaser tự tạo công việc mới hay đảm bảo timing.

Một chính sách khác:

```java
Phaser limited = new Phaser(3) {
    @Override
    protected boolean onAdvance(int phase, int registeredParties) {
        return phase >= 1 || registeredParties == 0;
    }
};
```

Đây là snippet trong phương thức. Nó chấm dứt sau giai đoạn phù hợp (khi advance từ phase 1), hoặc khi hết parties. **Không** gọi `register()`/`arrive()`/`awaitAdvance()` của chính phaser từ trong onAdvance: Javadoc cảnh báo tác động không được xác định.

### 11.5. Giới hạn phase và wraparound

Phase bắt đầu từ 0, tăng sau mỗi lần advance; Javadoc nói sau `Integer.MAX_VALUE` sẽ quay về 0. Đừng dùng phase như một mã batch toàn cục vĩnh viễn duy nhất, hay tính `newPhase - oldPhase` như đơn vị tuyệt đối của lifetime rất dài mà không xét wraparound/termination.

## 12. Những lỗi khiến barrier treo

### 12.1. Đăng ký nhiều hơn số workers thật

```java
Phaser p = new Phaser(1);
p.bulkRegister(5);
// Chỉ submit 4 workers, controller đợi stage 0.
p.arriveAndAwaitAdvance(); // Có thể chờ mãi vì slot thứ 5 không đến.
```

Đây là **anti-pattern**, không chạy để thử. Nếu gặp submit bị từ chối, cần dọn nghĩa vụ của task chưa launch, hoặc forceTerminate batch.

### 12.2. Quên controller là party

```java
Phaser p = new Phaser(1);
p.bulkRegister(3); // Tổng 4, không phải 3.
```

Nếu chỉ ba workers arrive và controller không arrive, còn một unarrived party. Khi controller chỉ muốn **quan sát phase** chứ không tham gia, có thể dùng `new Phaser(0)` + bulkRegister(workers), rồi `awaitAdvance(currentPhase)` từ observer **không đăng ký**.

### 12.3. arrive() hai lần cho một party trong cùng phase

Phaser không giữ thread identity nên nhiều lời gọi `arrive()` không có “token xác thực”. Nếu code gọi arrive hai lần cho cùng logical party, counter giảm sai hoặc có thể ném `IllegalStateException` khi unarrived âm. Đặc biệt nguy hiểm: lỗi có thể chỉ biểu hiện trong một thao tác sau.

**Hãy giữ trạng thái logic mỗi worker chỉ arrive đúng một lần mỗi phase.**

### 12.4. Đăng ký nhưng task không được chạy

ExecutorService có thể ném `RejectedExecutionException` khi pool đã shutdown hoặc queue quá tải. Vì thế registration trước submit phải đi kèm quản lý submission failure; không chỉ log lỗi rồi bỏ qua slot đã đăng ký.

### 12.5. Đợi trong pool nhỏ hơn số tasks đang chặn

Ví dụ ba tasks phải cùng tới barrier, nhưng pool chỉ có một worker; task đầu đã chạy, block ở barrier, tasks còn lại đang queue. Đó là starvation do thiết kế pool, không phải Phaser bị lỗi.

### 12.6. Đợi sai phase

`awaitAdvance(phase)` trả ngay nếu current phase khác phase được truyền. Nếu bạn đọc `getPhase()` quá muộn hoặc dùng phase cũ, nó có thể không chờ như kỳ vọng. Nên dùng **giá trị trả về của arrive()/arriveAndDeregister()** khi cần đợi phase tương ứng.

### 12.7. Đăng ký trên phaser đã terminated

Kết quả âm nghĩa là registration **không có hiệu lực**. Nếu vẫn submit worker và nghĩ đã đăng ký, worker có thể bỏ qua barrier, lỗi synchronization hoặc báo sai số hoàn thành. Kiểm tra giá trị return.

### 12.8. Nuốt lỗi của worker

Worker ném exception trước khi arrive, các parties khác có thể đợi mãi. Cần `forceTermination` hoặc chính sách arriveAndDeregister đúng trạng thái, đồng thời propagate lỗi qua Future/CompletionStage/callback. Không coi “worker kết thúc vì lỗi” là “worker đã báo đến barrier”.

## 13. Timeout, interruption và dọn party khi có lỗi

### 13.1. arriveAndAwaitAdvance() không phải wait có timeout

`arriveAndAwaitAdvance()` là cách đơn giản, nhưng nó **không có overload timeout**. Khi cần timeout:

```java
int current = phaser.arrive();
try {
    int next = phaser.awaitAdvanceInterruptibly(
            current, 5, TimeUnit.SECONDS);
    if (next < 0) {
        // Phaser terminated; xử lý failure/shutdown.
    }
} catch (TimeoutException timeout) {
    phaser.forceTermination();
    // Báo deadline failure tới owner.
} catch (InterruptedException interrupted) {
    phaser.forceTermination();
    Thread.currentThread().interrupt();
}
```

Đây là **snippet trong phương thức**. Caller phải là registered party khi gọi `arrive()`; cần imports `Phaser`, `TimeUnit` và `TimeoutException`. `arrive()` xảy ra **một lần trước khi đợi**, nên sau timeout **không gọi arrive lại**. ForceTermination giải phóng những waiters khác, không làm toàn bộ nghiệp vụ rollback.

### 13.2. awaitAdvance không interruptible theo nghĩa thoát khi interrupt

Javadoc mô tả `awaitAdvance(int)` tiếp tục đợi ngay cả nếu waiter bị interrupt. Khi cần báo lỗi kịp thời theo interrupt policy, dùng `awaitAdvanceInterruptibly(...)` và xử lý checked exception. Không giả định interrupt sẽ giải phóng party khác khỏi barrier.

### 13.3. Timeout không tự deregister

Nếu thread timeout khi đang chờ, phaser **vẫn giữ registered party** trừ khi bạn chủ động điều phối vòng đời. Nếu cancellation là toàn batch, `forceTermination()` thường đơn giản và an toàn hơn việc từng worker tự đoán mình cần arrive/deregister mấy lần.

### 13.4. Không double arrive trong finally

Sai:

```java
phaser.arrive(); 
try {
    phaser.awaitAdvanceInterruptibly(phase);
} finally {
    phaser.arriveAndDeregister(); // Sai nếu đây vẫn là phase đã arrive.
}
```

Đây là **anti-pattern**: `arriveAndDeregister()` vừa làm arrival **thêm lần nữa**, dù party đã arrive rồi. Nếu cần kết thúc participation sau một arrival nhưng trước phase tiếp theo, thiết kế giao thức đăng ký/termination phù hợp; đừng gọi hai arrival ở cùng phase.

Với workflow đơn giản, có thể để một worker **chỉ gọi `arriveAndDeregister()` tại phase cuối**, không gọi `arrive()` riêng ở phase cuối. Ở các phase trước, gọi `arriveAndAwaitAdvance()` mỗi phase đúng một lần.

## 14. Register không có per-party bookkeeping: hệ quả thiết kế

Đây là một chi tiết cốt lõi được Javadoc nhấn mạnh:

> Register/deregister chỉ cập nhật counters; không lưu danh tính từng party.

Vì thế `Phaser` không có:

- `isRegistered(Thread)`.
- `removeParty(partyId)`.
- Danh sách public các Thread đã đăng ký.
- Một registration handle để cancel tự động.
- Cơ chế “party 123 chỉ có thể arrive đúng một lần”.
- Mapping từ lô bulkRegister(n) sang n Future objects.

Nếu business muốn quản lý chính xác:

```text
Application PartyLease
    ├── batchId
    ├── taskId
    ├── registeredAtPhase
    ├── hasArrivedForCurrentPhase
    ├── deregistered
    └── owner: task/session
             |
             v
           Phaser counters
```

Đây là **mẫu kiến trúc ở tầng ứng dụng**, không phải lớp Java tiêu chuẩn. Mỗi lease cần owner và transitions thread-safe để tránh duplicate arrival, forgotten slot và cleanup sai.

### 14.1. Ai gọi register không quan trọng bằng ai chịu arrival

Một thread controller có thể gọi `bulkRegister(10)` thay mặt 10 tasks. Mỗi task sau đó gọi một arrival mỗi phase. Đây là cách sử dụng hợp lệ; Phaser không bắt buộc cùng thread gọi register và arrive.

### 14.2. bulkRegister không sinh party IDs

`bulkRegister(10)` trả **một** phase number, không phải một collection 10 tokens. Nếu task A hoặc B bị hủy, tầng app phải biết slot nào còn nghĩa vụ; Phaser không tự nhận diện.

### 14.3. Monitor không thay protocol

`getRegisteredParties()` chỉ là số lượng; nó không nói ai chưa đến. `getUnarrivedParties() == 0` có thể xuất hiện rất ngắn trước phase advance. Đừng poll các getters để quyết định “hủy worker X”; dùng futures, task registry và thông điệp thành công/thất bại ở tầng app.

## 15. Parent-child Phaser và bulkRegister

Để giảm contention khi **rất nhiều parties** hoạt động, Phaser có thể được tổ chức thành cấu trúc cây:

```java
Phaser root = new Phaser();
Phaser childA = new Phaser(root);
Phaser childB = new Phaser(root);
childA.bulkRegister(10);
childB.bulkRegister(10);
```

Đây là snippet trong phương thức. Khi child từ 0 parties tăng lên một số dương, **child tự đăng ký với parent** như một party tại parent. Khi child giảm về 0 qua `arriveAndDeregister()`, nó tự deregister khỏi parent.

Sơ đồ:

```text
Root Phaser
   |
   +-- Child A (10 local parties)
   |        10 local arrivals -> Child A reports one arrival upward
   |
   +-- Child B (10 local parties)
            10 local arrivals -> Child B reports one arrival upward

Root advances when its registered children/parties have arrived
```

Đừng suy root có 20 parties: root thường quản lý **mỗi child đang active như một party**, không phải mỗi task con một party trực tiếp. Việc lập cây có thêm overhead và phức tạp lifecycle; chỉ dùng khi đo được contention cần cải thiện.

### 15.1. Không tự gọi parent.register cho child đã có parent

Constructor và API registration/deregistration của child đã quản lý mối quan hệ parent tự động. Nếu application cũng tự thêm một manual parent party cho cùng child và quên arrive, root có thể treo.

### 15.2. bulkRegister(0) trên child không đăng ký child lên parent

Nếu child chưa có parties, `bulkRegister(0)` là no-op: child không chuyển từ empty sang active và không tạo một parent registration. Khi `bulkRegister(n)` với n dương, child chuyển 0 sang >0 và tự đăng ký parent.

### 15.3. Hiệu năng tiering

Đa số bài toán nhỏ/ít parties không cần tiering. Khi số participants lớn và contention nặng, tree Phaser có thể tăng throughput; nhưng chi phí truyền phase qua các cấp cũng tăng. Benchmark thay vì xem tiering là mặc định.

## 16. So sánh Phaser với CountDownLatch và CyclicBarrier

| Tiêu chí | `CountDownLatch` | `CyclicBarrier` | `Phaser` |
| --- | --- | --- | --- |
| Reusable nhiều phase | **Không** (latch một lần) | Có | Có |
| Số participants tăng/giảm động | Không | Không, số parties cố định | **Có: register/bulkRegister/deregister** |
| Cách participant báo đến | `countDown()` | `await()` | `arrive/arriveAndAwaitAdvance/arriveAndDeregister` |
| Đến nhưng không đợi | Có qua countDown | Không qua await | Có qua arrive |
| Có phase number | Không | Có generation nội bộ, không cùng API public | Có, `getPhase()`/return values |
| Trạng thái lỗi và chấm dứt | Đợi latch count hết | Barrier có thể broken/reset | Termination qua onAdvance/forceTermination |
| Lô participants đăng ký một lần | Count cố định lúc tạo | Count cố định lúc tạo | `bulkRegister(n)` |

Dùng Phaser khi **số parties thay đổi qua thời gian** hoặc cần nhiều phase và có thể tách arrival khỏi waiting. Nếu chỉ đợi một nhóm tasks hoàn tất một lần, `CountDownLatch` hoặc `CompletableFuture.allOf` có thể đơn giản hơn. Nếu số participants cố định và chỉ có một loại barrier, `CyclicBarrier` có thể dễ hiểu. Không chọn Phaser chỉ vì API “mới hơn” — tất cả các API này vẫn hữu ích tùy hoàn cảnh.

## 17. Memory visibility và dữ liệu chia sẻ

Phaser không chỉ đếm: Java SE 17 Javadoc mô tả **memory consistency effects**. Các hành động trước một lần arrival **happen-before** phase advance và `onAdvance` (nếu có), và phase advance happens-before các hành động sau khi phase đã tiến.

Điều này cho phép worker:

1. Ghi kết quả vào vùng nhớ đúng ownership.
2. Gọi `arriveAndAwaitAdvance()`.
3. Sau khi barrier advance, các parties khác đọc kết quả đã công bố trước arrival.

Tuy nhiên cần phân biệt:

- Phaser **không giải quyết data race** nếu hai workers đồng thời ghi cùng một biến không đồng bộ **trước barrier**.
- Barrier chỉ sắp thứ tự dữ liệu qua giai đoạn; cần chia vùng không chồng lấp, immutable objects, atomics hoặc locks để giải quyết concurrent writes.
- Trong BatchWorkersDemo, `AtomicIntegerArray` dùng cho counters; barrier bảo đảm mọi stage update đã xảy ra trước khi controller đọc sau advance.
- Không thực hiện đọc/ghi dữ liệu của stage kế tiếp khi một worker vẫn chưa hoàn thành barrier của stage trước, trừ khi thiết kế cho phép rõ ràng.

### 17.1. Điều gì nếu controller không registered?

Một observer chỉ gọi `awaitAdvance(phase)` cũng có thể chờ phase tiến, nhưng nó **không làm thay đổi số parties**. Nếu business cần controller quyết định khi stage kết thúc, controller nên là registered party và arrive; nếu chỉ theo dõi passive, observer mode có thể đủ. Chọn mô hình nhất quán.

## 18. Giới hạn dung lượng và hiệu năng của registration

Phaser có **maximum số registered parties** mà implementation hỗ trợ. Khi cố tăng quá giới hạn, `register()`/`bulkRegister(n)` có thể ném `IllegalStateException`. Không ép một Phaser đơn lẻ xử lý số lượng không giới hạn; cân nhắc tiering hoặc nhiều nhóm nhiệm vụ khi bài toán lớn.

### 18.1. bulkRegister có luôn nhanh hơn n lần register?

Một lời gọi bulk có thể giảm số lần cập nhật/phương thức so với lặp n lần `register()`, đặc biệt khi đăng ký lô. Nhưng lợi ích đo được còn phụ thuộc contention, platform và cách bạn submit/organize tasks. Đừng dùng bulkRegister(1000000) chỉ để thử tốc độ khi đã có giới hạn parties.

### 18.2. Register không phải “reserve CPU capacity”

Đăng ký 100 parties không tăng số threads trong executor hay số lõi CPU. Nếu mỗi worker tới barrier rồi block mà pool không có đủ worker capacity cho số tasks đang chờ, có nguy cơ deadlock/starvation. Phaser chỉ kiểm soát **điều kiện phase advance**, không lập lịch CPU.

### 18.3. Đừng poll counters trong tight loop

`getRegisteredParties()` và `getUnarrivedParties()` là monitoring snapshots, không phải primitive waiting. Busy-spin liên tục vừa tốn CPU vừa có thể quan sát trạng thái thay đổi bất ngờ. Dùng `arriveAndAwaitAdvance`/`awaitAdvance`/timeout API để đợi thực sự.

## 19. Ngoại lệ quan trọng

| Tình huống | Hành vi/exception | Cách xử lý |
| --- | --- | --- |
| `bulkRegister(-1)` | `IllegalArgumentException` | Validate n không âm |
| `register` vượt số parties tối đa | `IllegalStateException` | Tách nhóm/tier nếu phù hợp |
| `bulkRegister(n)` vượt capacity | `IllegalStateException` | Giảm batch, không cố ghi vượt |
| `register/bulkRegister` trên phaser terminated | Trả **phase âm**, không thêm party | Không submit task đã đăng ký thất bại |
| Party `arrive()` dư trong một phase | Usage error, có thể `IllegalStateException` | Track mỗi party đến đúng một lần |
| Party `arriveAndDeregister()` khi không còn registered | Usage error | Quản lý ownership/double cleanup |
| `awaitAdvanceInterruptibly` bị interrupt | `InterruptedException` | Không tự dereg, xử lý interrupt policy |
| Timed await vượt deadline | `TimeoutException` | Xử lý failure/cancel và phase lifecycle |
| `arriveAndAwaitAdvance` thấy phaser terminated | Return âm | Bỏ flow success, cleanup |
| Worker throw trước barrier | Có thể làm các party khác chờ | Force terminate hoặc coordination hợp lệ |
| Task submit bị reject sau bulkRegister | `RejectedExecutionException` | Reconcile slots/chấm dứt batch |
| `onAdvance` ném unchecked exception | Propagate đến party làm advance; không advance | Không dùng handler nặng/lỗi |
| `forceTermination()` | Chuyển trạng thái terminated | Dọn workers/tasks; không phải rollback |

Một chi tiết cần ghi nhớ: một lần arrival **không hợp lệ** có thể không bị phát hiện ngay vì Phaser không quản lý party identity. Đừng viết logic phụ thuộc ngoại lệ chắc chắn xuất hiện ngay khi có double-arrival.

## 20. Những lỗi thường gặp

**1. “register() tạo thread mới.”** Sai; nó chỉ thêm một nghĩa vụ chưa đến trong phaser.

**2. “register() trả ID của party.”** Sai; trả phase mà registration áp dụng.

**3. “bulkRegister(3) đặt tổng parties bằng 3.”** Sai; nó cộng **3 parties** vào count hiện tại.

**4. “bulkRegister(0) giải phóng các waiters.”** Sai; không thêm, không arrive, không deregister.

**5. “Nếu register trả -1 thì vẫn có thể xem như party được thêm.”** Sai; giá trị âm là registration không có hiệu lực do terminated.

**6. “Phaser tự biết Thread A đã register hay chưa.”** Sai; không có per-thread bookkeeping.

**7. “Cùng thread gọi register thì phải là thread gọi arrive.”** Không; registration theo logical party, không ràng buộc thread identity.

**8. “Worker tự register lúc nào cũng thuộc phase kế tiếp.”** Sai; phase return cho biết được áp dụng ở đâu, có thể phase hiện tại.

**9. “Đọc getPhase() rồi register là thao tác atomic.”** Sai; phase có thể tiến giữa hai lời gọi.

**10. “Phaser với 0 parties luôn terminated.”** Sai khi mới tạo `new Phaser()`; active phase 0.

**11. “Deregister cuối cùng chỉ giảm count, phaser vẫn reusable mặc định.”** Sai; default onAdvance có thể terminate khi registered về 0.

**12. “Phaser terminated có thể register lại để hồi sinh.”** Sai; register trả phase âm, không thêm.

**13. “arrive() làm party rời khỏi tất cả phase sau.”** Sai; chỉ đánh dấu đã đến phase hiện tại.

**14. “arriveAndDeregister() chỉ xóa registration, không đánh dấu arrival.”** Sai; nó làm cả hai.

**15. “awaitAdvance() tự đánh dấu arrival.”** Sai; nó chỉ đợi phase thay đổi.

**16. “arriveAndAwaitAdvance() không block.”** Sai; nó có thể đợi các parties khác.

**17. “arriveAndAwaitAdvance() có sẵn tham số timeout.”** Không; dùng arrive() và awaitAdvanceInterruptibly(...timeout...).

**18. “Timed await tự xóa party khỏi phaser.”** Sai; timeout/interrupt không tự đổi registration/arrival.

**19. “Sau await timeout cứ gọi arriveAndDeregister trong finally.”** Không chắc đúng nếu party đã arrive; có thể double arrival.

**20. “Nếu worker bị lỗi thì barrier tự biết thiếu một party.”** Sai; app phải reconcile hoặc forceTermination.

**21. “bulkRegister N rồi chỉ submit N-1 jobs cũng không sao.”** Sai; thiếu một arrival, có thể treo.

**22. “Pool 1 thread có thể làm 10 worker tasks đều chờ barrier vì scheduler sẽ lần lượt chạy.”** Không nếu worker đầu chặn và các task còn lại chưa chạy; nguy cơ starvation.

**23. “getUnarrivedParties() là lock-free signal đủ để quyết định tất cả workers xong.”** Sai; chỉ monitoring snapshot.

**24. “Parent phaser luôn đếm từng child worker một cách trực tiếp.”** Sai; hierarchical phaser thường đăng ký active child như một party với parent.

**25. “bulkRegister(0) trên child sẽ register child với parent.”** Sai; không tạo party.

**26. “forceTermination làm mọi business writes rollback.”** Sai; nó chỉ giải phóng synchronization waiters.

**27. “Phaser giải quyết mọi data race của stage.”** Sai; barrier chỉ thiết lập ordering tại phase boundaries.

**28. “Có thể gọi register/arrive bên trong onAdvance mà không rủi ro.”** Javadoc không đặc tả tác động; tránh.

**29. “register/bulkRegister không bao giờ đợi.”** Sai; có thể chờ onAdvance đang chạy.

**30. “Không cần giới hạn số parties.”** Sai; có maximum supported và còn rủi ro tài nguyên.

## 21. Checklist review

- [ ] Đã xác định rõ ai là **logical party owner**, không dựa vào thread identity?
- [ ] Biết controller/main có được tính vào registered parties hay chỉ quan sát?
- [ ] Nếu controller có `new Phaser(1)`, nó có arrive/deregister đúng mỗi phase?
- [ ] Khi tạo batch workers, có dùng `bulkRegister(n)` **trước** khi submit nếu cần tránh early advance?
- [ ] `n` là số parties bổ sung, không phải số parties tổng?
- [ ] Có kiểm tra phase return âm của register/bulkRegister?
- [ ] Có validate `n >= 0` và capacity khi bulk-register?
- [ ] Có xử lý `bulkRegister(0)` là no-op?
- [ ] Đăng ký muộn có protocol admission/gating rõ ràng?
- [ ] Không giả định `getPhase()` đọc trước register là phase áp dụng registration?
- [ ] Đã xác định mỗi worker chịu arrival ở những phases nào?
- [ ] Không double arrive/deregister cho một party tại cùng phase?
- [ ] Worker muốn rời nhóm dùng `arriveAndDeregister()` đúng lúc?
- [ ] Nếu submit thất bại sau registration, có reconcile slots còn thiếu?
- [ ] Nếu worker lỗi, có termination/recovery policy để không treo waiters?
- [ ] Không nuốt TimeoutException/InterruptedException mà bỏ mặc phaser?
- [ ] Nếu cần timeout, có dùng `awaitAdvanceInterruptibly` đúng và không double arrival?
- [ ] Không biến `getUnarrivedParties()` thành một busy-spin loop?
- [ ] Có hiểu register có thể đợi onAdvance đang thực thi?
- [ ] onAdvance ngắn gọn, không gọi lại register/await của cùng phaser?
- [ ] Có hiểu phaser mặc định terminate khi cuối cùng deregister về 0?
- [ ] Có kiểm tra `isTerminated()` trước khi tái dùng object?
- [ ] Có tách batch mới sang phaser mới nếu batch trước terminated?
- [ ] Nếu dùng override onAdvance, termination policy và edge cases được test?
- [ ] Nếu dùng tree Phaser, có tránh đăng ký thủ công parent thêm lần nữa?
- [ ] Worker pool đủ capacity để các registered parties có thể tới barrier?
- [ ] Dữ liệu chia sẻ trước/qua phase được publish/đọc theo memory ordering đúng?
- [ ] Tests kiểm tra stage counts, phases và cleanup mà không phụ thuộc thread scheduling?
- [ ] Benchmark khi có số parties lớn, tránh registration/unregistration overhead thừa?
- [ ] Kết quả Java tương thích Java 17+; không dùng API legacy?

## 22. Câu hỏi tự đánh giá

**1.** `register()` thêm bao nhiêu parties? — Một **unarrived party**.

**2.** `bulkRegister(5)` thêm bao nhiêu? — Năm parties bổ sung.

**3.** `bulkRegister(0)` làm gì? — Không thay đổi parties, trả phase hiện tại.

**4.** `bulkRegister(-2)` gây gì? — IllegalArgumentException.

**5.** `register()` trả giá trị nào? — Phase number mà registration được áp dụng.

**6.** Giá trị trả về âm nghĩa gì? — Phaser terminated, registration không có hiệu lực.

**7.** Register có tạo Java Thread không? — Không.

**8.** Phaser có lưu danh tính mỗi party không? — Không, chỉ đếm.

**9.** `new Phaser()` có bao nhiêu parties? — 0, ban đầu chưa terminated.

**10.** `new Phaser(1)` có thể đại diện cho ai? — Controller/main, nếu controller cũng phải arrive.

**11.** `getRegisteredParties()` cho biết gì? — Tổng parties đã đăng ký tại thời điểm quan sát.

**12.** `getUnarrivedParties()` cho biết gì? — Số parties chưa đến current phase, là snapshot.

**13.** `arrive()` có deregister không? — Không.

**14.** `arriveAndDeregister()` khác arrive thế nào? — Vừa đến vừa rời registration.

**15.** `arriveAndAwaitAdvance()` có thể block không? — Có.

**16.** `awaitAdvance(phase)` có tự arrive không? — Không.

**17.** Unregistered observer được gọi awaitAdvance không? — Có, nhưng nó không thay đổi counters.

**18.** Đăng ký muộn có thể tăng số unarrived của phase hiện tại không? — Có.

**19.** Làm sao biết registration áp dụng phase nào? — Dùng return của `register/bulkRegister`.

**20.** register có thể phải đợi khi nào? — Khi onAdvance đang thực thi.

**21.** Nếu tất cả parties deregister, phaser mặc định sẽ ra sao? — Terminated.

**22.** Phaser terminated có register lại được không? — Không có hiệu lực, trả phase âm.

**23.** Có thể giữ phaser active khi parties về 0 không? — Có thể override onAdvance trả false, với protocol phù hợp.

**24.** `forceTermination()` giải quyết chuyện gì? — Buộc kết thúc phase synchronization và giải phóng waits.

**25.** Timed `awaitAdvanceInterruptibly` timeout có tự deregister không? — Không.

**26.** Vì sao bulkRegister trước submit workers? — Tránh phase advance khi chưa đăng ký đủ nghĩa vụ.

**27.** Nếu worker bị lỗi trước arrival, ai xử lý? — Owner/application, có thể force terminate/reconcile parties.

**28.** Vì sao pool quá ít worker threads có thể deadlock? — Worker đầu block ở barrier làm tasks còn lại không được chạy.

**29.** Phaser có thay locks cho mutable shared state không? — Không; vẫn phải tránh data race.

**30.** Khi nào nên dùng hierarchical Phaser? — Khi contention lớn và benchmark chứng minh tree có lợi.

## 23. Tài liệu chính thức — Java SE 17

- [Phaser — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Phaser.html): registration, bulkRegister, arrivals, dynamic parties, hierarchical phasers, termination, memory consistency effects.
- [CountDownLatch — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): barrier một lần với count cố định.
- [CyclicBarrier — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CyclicBarrier.html): cyclic barrier với số parties cố định.
- [ExecutorService — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): submit, Future, shutdown và rejection handling.
- [AtomicIntegerArray — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicIntegerArray.html): counters thread-safe.
- [TimeoutException — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/TimeoutException.html): timeout khi chờ một đồng bộ có giới hạn thời gian.

**Ghi nhớ:** `register()` thêm **một** party, `bulkRegister(n)` thêm **n** parties, và cả hai trả về **phase áp dụng registration** chứ không phải ID party. Đăng ký mới tăng số arrivals còn thiếu; nếu diễn ra giữa phase nó có thể kéo dài barrier hiện tại. `arrive()` chỉ báo đến, `arriveAndAwaitAdvance()` báo đến rồi đợi, còn `arriveAndDeregister()` báo đến đồng thời rời nhóm. Registration/deregistration **không lưu danh tính thread**, nên ứng dụng phải quản lý ownership, lỗi task, cleanup và tránh double arrival. Khi phaser mặc định về 0 parties do deregistration, nó terminated và không thể register lại; dùng phaser mới hoặc override onAdvance với chính sách rõ.