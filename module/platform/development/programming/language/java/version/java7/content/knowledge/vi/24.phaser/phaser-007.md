# Phaser trong Java: Chờ có thể ngắt hoặc hết thời hạn

## 1. Mục tiêu bài học

`java.util.concurrent.Phaser` xuất hiện trong **Java 7** và vẫn là đồng bộ hóa theo giai đoạn (*phase-based barrier*) hữu ích trong **Java 17+**. Khác với một latch dùng một lần, Phaser có thể đi qua nhiều phase, cho phép các bên tham gia (*parties*) đăng ký, đến điểm đồng bộ và rời nhóm theo vòng đời công việc.

Bài **“Chờ có thể ngắt hoặc hết thời hạn”** tập trung vào hai phương thức:

```java
int next = phaser.awaitAdvanceInterruptibly(phase);

int nextWithDeadline = phaser.awaitAdvanceInterruptibly(
        phase, timeout, TimeUnit.MILLISECONDS);
```

Đây là snippet: `phaser`, `phase` và `timeout` cần được định nghĩa, caller xử lý `InterruptedException` và, với overload thời hạn, `TimeoutException`.

Sau bài học cần hiểu rõ:

- Phân biệt **ghi nhận một party đã đến** (`arrive`) với **đợi phase thay đổi** (`awaitAdvance...`).
- `arriveAndAwaitAdvance()` và `awaitAdvance(int)` là hai cách **chờ không ném InterruptedException và không có timeout tích hợp**.
- `awaitAdvanceInterruptibly(int)` có thể ném `InterruptedException` khi thread chờ bị ngắt.
- `awaitAdvanceInterruptibly(int,long,TimeUnit)` có thể ném cả `InterruptedException` lẫn `TimeoutException`.
- **Interrupt/timeout trong một lời chờ không tự thay đổi phase, số parties hay arrival counts.**
- Một party đã gọi `arrive()` **không được tự gọi lại arrival ở cùng phase** chỉ vì chờ bị timeout.
- `forceTermination()` là một lựa chọn phục hồi khi cả đợt không còn thể tiếp tục, không phải thao tác cancel mọi công việc nghiệp vụ.
- Phải phân biệt **phase tiến bình thường**, **phase đã tiến trước khi bắt đầu chờ**, **timeout**, **interrupt** và **Phaser terminated**.

Đây đều là kiến thức còn hiệu lực trong Java SE 17+. Mã Java cuối bài đã được biên dịch và chạy thực tế, có output chính xác và không phụ thuộc `Thread.sleep` để đồng bộ concurrency test.

## 2. Nền tảng: registered parties, arrival và phase number

### 2.1. Registered party là gì?

Mỗi party đại diện cho một bên mà Phaser dự kiến sẽ **đến** trong một phase. Có thể tạo trực tiếp:

```java
Phaser phaser = new Phaser(2);
```

Phaser này bắt đầu tại **phase 0** với **2 registered parties**, cả hai đều chưa đến. Các phương thức quan sát gồm:

- `getPhase()`: phase hiện tại, từ 0 và tăng khi mọi party đã đến. Khi terminated, giá trị âm.
- `getRegisteredParties()`: tổng số parties đã đăng ký.
- `getArrivedParties()`: số parties đã đến của phase hiện tại.
- `getUnarrivedParties()`: số parties còn phải đến của phase hiện tại.
- `isTerminated()`: Phaser đã vào trạng thái kết thúc hay chưa.

`getArrivedParties()`/`getUnarrivedParties()` là **snapshot để quan sát/diagnostic**. Khi Phaser đã terminated, Javadoc nói số arrived/unarrived có thể **không còn ý nghĩa**; không thiết kế nghiệp vụ dựa trên chúng sau termination.

Phaser không theo dõi danh tính thread nào là party: `register/arrive/deregister` điều chỉnh bộ đếm, không tạo danh sách “thread X đăng ký”. Ứng dụng phải tự quản lý ownership của mỗi arrival, không gọi nhiều lần vì lầm tưởng mỗi thread đương nhiên sở hữu riêng một slot.

### 2.2. `arrive()`: đến mà không chờ

```java
int phase = phaser.arrive();
```

`arrive()` đánh dấu **một party đã đến phase hiện tại** và trả **phase áp dụng cho arrival đó**. Nếu chưa đủ arrivals, phase không đổi. Nếu vừa là party cuối cùng cần đến, lời gọi có thể làm phase tiến lên.

`arrive()` **không tự đợi**, vì vậy rất thích hợp để tách bước “đã hoàn thành phần việc của phase” khỏi bước “có muốn chờ những party khác hay không”.

### 2.3. `awaitAdvance(phase)`: chỉ đợi thay đổi phase

```java
int arrivedAt = phaser.arrive();
int nextPhase = phaser.awaitAdvance(arrivedAt);
```

`awaitAdvance` đợi đến khi phase hiện tại **khác với `arrivedAt`** hoặc Phaser terminated. `awaitAdvance` **không tự tăng arrival count**, vì caller đã làm điều đó bằng `arrive()`.

Quan trọng: một thread **không phải party** vẫn có thể đọc `int phase = phaser.getPhase()` và gọi `awaitAdvance(phase)` như một **observer**. Observer không bắt buộc phải đến barrier; không gọi `arrive()` nếu chưa được tính trong registered parties.

### 2.4. Trình tự hai party đi qua barrier

```text
Phaser(2), phase=0, registered=2, unarrived=2

Party A: arrive() -> returns phase 0
         unarrived=1
         awaitAdvanceInterruptibly(0, 2, SECONDS)
                | waits...
Party B: arrive() -> returns phase 0
         unarrived=0 => phase becomes 1
                |
Party A: await returns phase 1
Party B: can observe phase 1
```

Chỉ đến lúc **đủ arrivals**, phase mới tiến. Deadline/interrupt là khả năng của **caller đang chờ**, không phải lệnh tự động giảm tổng số parties.

## 3. Năm API chờ/đến cần phân biệt

| API | Ghi nhận arrival? | Đợi? | Interruptible? | Timeout tích hợp? | Giá trị chính |
| --- | --- | --- | --- | --- | --- |
| `arrive()` | **Có** | Không | Không chờ | Không | Arrival phase |
| `arriveAndAwaitAdvance()` | **Có** | Có | **Không** | Không | Phase mới hoặc số âm nếu terminated |
| `awaitAdvance(phase)` | Không | Có nếu phase còn trùng | **Không** | Không | Phase sau khi đổi/termination |
| `awaitAdvanceInterruptibly(phase)` | Không | Có nếu phase còn trùng | **Có** | Không | Phase mới hoặc `InterruptedException` |
| `awaitAdvanceInterruptibly(phase, timeout, unit)` | Không | Có nếu phase còn trùng | **Có** | **Có** | Phase mới hoặc checked exception |

Ngoài ra `arriveAndDeregister()` vừa ghi nhận arrival vừa **rút party khỏi các phase sau**, không chờ. Nó không phải “cancel lời chờ” nếu party đã `arrive()` trong chính phase đó.

Theo Oracle Java SE 17, `arriveAndAwaitAdvance()` tương đương về tác dụng với `awaitAdvance(arrive())`. Nếu cần wait có interrupt hoặc timeout, tách arrival khỏi waiting:

```java
int current = phaser.arrive();
int next = phaser.awaitAdvanceInterruptibly(
        current, 5, TimeUnit.SECONDS);
```

**Cả hai dòng phải nằm trong policy xử lý `InterruptedException`/`TimeoutException`.** Trong môi trường nhiều threads, đừng đánh giá `getPhase()` rồi tự giả định nó chính là phase vừa ghi nhận arrival; dùng giá trị **trả về từ `arrive()`**.

## 4. Cách chờ có thể bị ngắt: `awaitAdvanceInterruptibly(int phase)`

### 4.1. Chữ ký

```java
public int awaitAdvanceInterruptibly(int phase)
        throws InterruptedException
```

Phương thức đợi phase chuyển từ giá trị `phase` sang phase khác. Nếu thread bị interrupt khi đang chờ, lời gọi **ném `InterruptedException`**. Còn nếu phase đã khác hoặc Phaser đã terminated, phương thức có thể **trả về ngay**.

Khác với `awaitAdvance(phase)`, overload này cho caller cơ hội phản hồi sớm khi hệ thống yêu cầu dừng thread chờ.

### 4.2. Mẫu bắt interruption

```java
int arrivalPhase = phaser.arrive();

try {
    int next = phaser.awaitAdvanceInterruptibly(arrivalPhase);
    if (next < 0) {
        throw new IllegalStateException("Phaser was terminated");
    }
    // Phase đã tiến.
} catch (InterruptedException interrupted) {
    Thread.currentThread().interrupt();
    // Chuyển sang policy phục hồi; không đến barrier lần thứ hai.
    phaser.forceTermination();
    throw interrupted;
}
```

Đây là **snippet trong một method khai báo `throws InterruptedException`** và **giả định scope này sở hữu toàn bộ Phaser/job**, nên được phép `forceTermination()`. Trong shared Phaser, một helper không thể tùy tiện forceTerminate toàn bộ hệ thống chỉ vì riêng mình bị interrupt; cần báo coordinator và tuân thủ policy của service.

**Khôi phục interrupt flag:** `InterruptedException` thường xóa cờ interrupted của thread khi được ném. Nếu code phải tiếp tục cleanup/propagate hoặc không muốn mất yêu cầu dừng, gọi `Thread.currentThread().interrupt()` trong catch (như trên). Không dùng vòng lặp nuốt `InterruptedException` rồi chờ mãi.

### 4.3. Interrupt không tự thay đổi Phaser

Cực kỳ quan trọng: khi `awaitAdvanceInterruptibly` ném `InterruptedException`, **registered parties và trạng thái arrival không tự thay đổi**. Nếu trước đó caller đã `arrive()`, nó vẫn được tính là đã đến cho phase đang chờ.

Ví dụ có 2 parties, A đã `arrive()`, B chưa đến: sau khi A bị interrupt khỏi wait, Phaser vẫn có 2 registered parties, chỉ 1 party đã đến và **1 party chưa đến**. Nếu B không bao giờ đến, các waiters khác vẫn có thể bị kẹt, trừ khi ứng dụng phục hồi hợp lệ.

### 4.4. Ngắt một thread không nhất thiết hủy công việc của party khác

`Thread.interrupt()` là tín hiệu tới **một thread**, không phải lời gọi broadcast tới mọi participant. Các threads khác có thể tiếp tục xử lý hoặc đang chờ bằng `awaitAdvance()` không ngắt được. Nếu toàn bộ job phải dừng, cần chính sách cancellation ở tầng ứng dụng và/hoặc `forceTermination()`.

Nếu caller đang chờ ở một phase **đã tiến trước khi gọi wait**, method có thể trả ngay mà không phát sinh `InterruptedException`. Không viết test khẳng định “đã set interrupt flag thì mọi lời gọi awaitAdvanceInterruptibly chắc chắn ném” mà bỏ qua trạng thái phase hiện tại.

## 5. Chờ có thời hạn: `awaitAdvanceInterruptibly(phase, timeout, unit)`

### 5.1. Chữ ký và kết quả

```java
public int awaitAdvanceInterruptibly(
        int phase, long timeout, TimeUnit unit)
        throws InterruptedException, TimeoutException
```

Có ba khả năng quan trọng:

1. **Phase tiến hoặc Phaser terminated:** trả phase hiện tại/giá trị termination theo contract.
2. **Thread bị interrupt trong lúc chờ:** ném `InterruptedException`.
3. **Thời hạn chờ trôi qua mà phase chưa đổi:** ném `TimeoutException`.

`timeout` là độ dài thời hạn chờ được diễn giải theo `TimeUnit`, **không phải thời điểm đồng hồ tuyệt đối**. Ví dụ `awaitAdvanceInterruptibly(phase, 3, TimeUnit.SECONDS)` chờ tối đa một khoảng ba giây.

### 5.2. Mẫu dùng ở boundary của job

```java
int phase = phaser.arrive();

try {
    int nextPhase = phaser.awaitAdvanceInterruptibly(
            phase, 3, TimeUnit.SECONDS);
    if (nextPhase < 0) {
        throw new IllegalStateException("Synchronization aborted");
    }
    // Tất cả party cần thiết đã đến, phase mới bắt đầu.
} catch (TimeoutException timedOut) {
    // Log timeout, yêu cầu coordinator xử lý bên chưa đến.
    phaser.forceTermination(); // Chỉ khi đây là owner của cả job.
    throw timedOut;
} catch (InterruptedException interrupted) {
    Thread.currentThread().interrupt();
    phaser.forceTermination(); // Cùng điều kiện ownership.
    throw interrupted;
}
```

Đây là snippet đặt trong method khai báo `throws InterruptedException, TimeoutException` và có import `java.util.concurrent.*`. **Chỉ coordinator/job owner mới được tự quyết định terminate một Phaser được chia sẻ**. Nếu job muốn retry hoặc cho party chậm thêm thời gian, phải có quyết định khác được các bên thống nhất.

### 5.3. Timeout không tự deregister

Phaser là barrier theo bộ đếm arrivals; khi thread đợi quá lâu:
- `getPhase()` vẫn ở phase hiện tại nếu chưa đủ arrivals.
- `getRegisteredParties()` vẫn như cũ.
- `getUnarrivedParties()` vẫn như cũ (nếu chưa có participant khác đến trong lúc chờ).
- Một party đã `arrive()` vẫn **đã đến** cho phase ấy.

`TimeoutException` không tự gọi `arriveAndDeregister()`, không xóa registration, không tiến phase và không hủy các workers khác. Không viết code “catch timeout rồi gọi `arrive()` lại để cứu barrier”; một party không được arrival hai lần trong một phase.

### 5.4. Deadline bằng 0 hay đã quá hạn

Nếu phase đã khác tham số ngay khi gọi, `awaitAdvanceInterruptibly(oldPhase, 0, NANOSECONDS)` có thể **trả ngay phase mới**, không ném timeout. Nếu phase vẫn chưa đổi, timeout 0/âm không tạo thời gian đợi có ích và có thể timeout tức thì.

Đừng đồng nhất “cấu hình timeout=0” với “method luôn ném `TimeoutException`”; **trạng thái phase** được xét trước khi quyết định có cần chờ.

### 5.5. Timeout và interrupt có thể đua nhau

Nếu interrupt xảy ra sát thời hạn timeout hoặc sát lúc phase chuyển, kết quả quan sát có thể chịu ảnh hưởng của scheduling/race. Unit test nên kiểm soát thứ tự bằng latches hoặc dùng phạm vi chấp nhận rõ ràng; không thiết kế logic nghiệp vụ đòi một thứ tự exception cứng nhắc khi hai sự kiện cạnh tranh.

## 6. Vì sao hai sự kiện interrupt/timeout không phá barrier tự động?

Phaser có ưu điểm tách **arrival** và **wait**. Một caller có thể bỏ chờ vì deadline nhưng phần việc đã hoàn thành tại phase ấy vẫn hợp lệ, và các party khác vẫn có thể đến sau. Nếu API tự ý giảm registration hoặc tự force termination mỗi lần một thread bị interrupt, một hoạt động phụ trợ sẽ làm hỏng việc đồng bộ của toàn job.

Do đó tài liệu Java SE 17 nói rõ: **exceptions khi chờ interruptibly/timed không làm đổi trạng thái Phaser**. Ứng dụng chịu trách nhiệm lựa chọn phục hồi:

- Tiếp tục để phase tiến khi party còn lại đến.
- Thông báo lỗi và ngừng gửi công việc mới.
- Nếu toàn bộ job đã thất bại, `forceTermination` để giải phóng những waiters.
- Thiết kế flow deregistration cho **phase tương lai** nếu một party không còn tham gia.
- Đảm bảo bên phụ trách work và tài nguyên không tiếp tục chạy trái policy.

Không có cơ chế “timeout riêng của party A tự thả barrier cho B” nếu B chưa arrival và vẫn đang được tính trong registered parties.

## 7. Không được đến hai lần trong cùng phase

### 7.1. Quy tắc một arrival / một registered party / mỗi phase

Một registered party tham gia phase thì **chỉ ghi một arrival** cho phase đó. Nếu đã gọi:

```java
int phase = phaser.arrive();
```

và `awaitAdvanceInterruptibly(phase, timeout, unit)` timeout, việc sau đây là **sai**:

```java
catch (TimeoutException timedOut) {
    phaser.arriveAndDeregister(); // Sai nếu vẫn cùng phase đã arrive.
}
```

Vì `arriveAndDeregister()` cũng **ghi nhận một arrival**, gọi khi party đã arrive trong cùng phase dẫn tới **double-arrival** và làm sai các bộ đếm, có thể gây `IllegalStateException` hoặc barrier tiến thiếu participant.

### 7.2. Chính sách phục hồi thay thế

Nếu toàn bộ job không còn đáng tiếp tục, owner có thể `forceTermination`, đưa Phaser vào trạng thái terminated để waiters trả về. Nếu chỉ một party muốn rút khỏi các phase sau nhưng phase hiện tại vẫn phải được hoàn tất, party đó phải:
1. Đã ghi arrival của current phase đúng một lần.
2. Cho current phase tiến một cách hợp lệ hoặc được coordinator xử lý.
3. Deregister **từ phase tiếp theo** khi có quyền arrival lần nữa, hoặc thiết kế vòng đời deregistration trước khi đã arrival ngay từ đầu.

Không cố chế ra một `unarrive()` hoặc `deregisterWithoutArrival()`: Phaser không cung cấp các method đó theo API Java 17.

### 7.3. Giai đoạn chờ và đăng ký là hai trách nhiệm riêng

Observer không phải registered party có thể chờ phase bằng `getPhase` + `awaitAdvanceInterruptibly` mà không gọi `arrive`. Trong trường hợp đó, timeout không tạo ra bất kỳ arrival nào để “xóa”. Nếu observer muốn trở thành participant, phải `register` tại thời điểm phù hợp với protocol.

## 8. `forceTermination()`: thoát trạng thái kẹt theo policy

### 8.1. Tác dụng thực tế

`forceTermination()` buộc Phaser vào trạng thái kết thúc:

- `isTerminated()` trở thành `true`.
- `getPhase()` là số **âm**.
- Những lời chờ Phaser đang đợi được đánh thức theo semantics termination.
- Những lời gọi đợi tới Phaser đã terminated trả về ngay với trạng thái termination âm theo contract.
- `getRegisteredParties()` **không bị giảm** chỉ vì gọi `forceTermination`.
- Trong hierarchical phasers, forceTermination của một node có thể terminate cả hệ phân cấp theo contract.

Ví dụ:

```java
Phaser phaser = new Phaser(2);
int phase = phaser.arrive();

phaser.forceTermination();
int ended = phaser.awaitAdvanceInterruptibly(
        phase, 1, TimeUnit.SECONDS);

System.out.println(phaser.isTerminated()); // true
System.out.println(ended < 0);             // true
```

Đây là snippet bên trong method có xử lý checked exceptions. `forceTermination()` không đóng network connections, files, không interrupt workers đang tính toán và không rollback database writes.

### 8.2. Dùng khi nào?

Phù hợp khi coordinator xác định barrier này **không thể tiếp tục dùng cho một lần đồng bộ hợp lệ**, ví dụ một participant thất bại không thể khôi phục, deadline chung đã hết hoặc service đang shutdown.

Không phù hợp nếu:
- Phaser còn phục vụ các request/parties độc lập.
- Chỉ một observer hết thời gian chờ nhưng job vẫn được phép tiếp tục.
- Muốn tạm nghỉ vài giây rồi tái sử dụng **cùng Phaser đã terminated**.
- Đang dùng forceTermination như thay thế cho cancellation signal dành cho worker bodies.

Nếu muốn thử lại một quy trình đã terminate, thường tạo **Phaser mới** theo vòng đời mới thay vì cố register lại vào một Phaser terminated.

### 8.3. Giá trị âm không phải phase thành công

`awaitAdvanceInterruptibly(...)` **không chỉ có hai kết quả “trả số” hoặc “ném exception”**. Nó có thể trả **số âm** khi terminated:

```java
int next = phaser.awaitAdvanceInterruptibly(
        phase, 2, TimeUnit.SECONDS);

if (next < 0) {
    // Phaser terminated, không báo success.
} else {
    // Phase đã thay đổi theo contract.
}
```

Đừng so sánh mỗi `next != phase` rồi ghi “SUCCESS” mà bỏ qua `next < 0`. Phase có thể tiến qua nhiều thế hệ trước khi caller quan sát, không nhất thiết chỉ tăng đúng 1 trong môi trường phức tạp.

## 9. Phân biệt chờ không interruptible và chờ interruptible

### 9.1. `awaitAdvance(phase)`

Theo tài liệu Java SE 17, `awaitAdvance(phase)` tiếp tục chờ **kể cả khi thread chờ bị interrupt**. Nó không ném `InterruptedException`. Java có thể bảo toàn/restoring interrupt status khi method quay về.

Nếu chương trình muốn phản hồi yêu cầu dừng trong thời gian chờ, sử dụng `awaitAdvanceInterruptibly` thay vì loop polling flag quanh `awaitAdvance` rồi hy vọng tỉnh dậy ngay.

### 9.2. `arriveAndAwaitAdvance()`

`arriveAndAwaitAdvance()` tương đương hiệu ứng `awaitAdvance(arrive())`. Nó rất tiện khi các participants đều cần barrier không timeout và không ngắt được. Nhưng nếu một participant bị mất hoặc thread cần dừng, lời chờ có thể kéo dài vô hạn nếu không có phase advancement hoặc termination.

Không có overload `arriveAndAwaitAdvance(timeout, unit)` theo API Java 17; muốn timed wait phải tách thành `arrive()` rồi `awaitAdvanceInterruptibly(...)`.

### 9.3. Bài test so sánh

Chương trình cuối bài dùng hai threads:

- Một thread gọi `awaitAdvanceInterruptibly` và nhận `InterruptedException` khi main thread gọi `interrupt()`.
- Thread khác gọi `awaitAdvance`; main thread interrupt nhưng cũng cho party cuối cùng đến để phase tiến. Worker vẫn trả về phase mới và **cờ interrupted được bảo toàn**.

Điều này chứng minh sự khác nhau về **khả năng rời lời chờ**, không phải về số parties: cả hai cách chờ đều không tự thay đổi arrival state.

## 10. Trường hợp phase đã thay đổi trước khi gọi wait

`awaitAdvanceInterruptibly(phase)` không phải một lệnh “luôn đợi một barrier kế tiếp”. Nó so sánh **phase hiện tại** với argument:

- Nếu bằng nhau, chờ.
- Nếu khác nhau, trả về ngay.
- Nếu Phaser terminated, trả về ngay theo trạng thái kết thúc.
- Nếu argument là số âm, trả ngay số âm ấy.

Ví dụ:

```java
Phaser phaser = new Phaser(1);
int oldPhase = phaser.getPhase(); // 0
phaser.arrive();                   // Party duy nhất đến: phase thành 1

int observed = phaser.awaitAdvanceInterruptibly(
        oldPhase, 0, TimeUnit.NANOSECONDS);
// observed == 1, không có TimeoutException.
```

Đây là snippet trong phương thức xử lý checked exceptions; để cleanup có thể `phaser.arriveAndDeregister()` **ở phase 1**, lúc đó mặc định Phaser terminated vì không còn party.

Điểm học được: phải truyền **phase mà caller thực sự muốn quan sát thay đổi**, thường là kết quả `arrive()`. Không truyền một phase tùy ý quá cũ và hiểu việc trả ngay là một lần barrier mới vừa hoàn tất.

## 11. Registration, deregistration và lifecycle nhiều phase

### 11.1. `register()` và `bulkRegister(int)`

`Phaser.register()` thêm một party chưa đến; `bulkRegister(n)` thêm n parties. Ứng dụng có thể thay đổi số participants giữa các phase, nhưng phải xác định rõ ai gọi và khi nào.

Nếu muốn đợi workers mới được tạo, cần đăng ký **trước khi** những workers được tính vào số parties phải đến, để barrier không tiến quá sớm. Đăng ký sai thời điểm có thể tạo deadlock hoặc bỏ sót một phase.

### 11.2. `arriveAndDeregister()`

Ghi arrival cho **phase hiện tại** đồng thời rút party khỏi các phase tiếp theo. Trong vòng đời bình thường:

```java
try {
    for (...) {
        int phase = phaser.arrive();
        int next = phaser.awaitAdvanceInterruptibly(
                phase, 10, TimeUnit.SECONDS);
        if (next < 0) break;
        // Work for next phase.
    }
} finally {
    // Chỉ deregister nếu party còn registered, chưa arrived
    // ở current phase và protocol cho phép arrival này.
}
```

Đây là **pseudocode**, vì một `finally { arriveAndDeregister(); }` vô điều kiện là sai nếu task đã arrive trong phase bị timeout/interrupt. Resource owner phải theo dõi trạng thái arrival của từng party ở từng phase.

### 11.3. Default termination khi không còn registered parties

Javadoc Java SE 17 giải thích `onAdvance` mặc định sẽ terminate Phaser khi một lần deregistration khiến số registered parties trở thành **0**. Khi đó `getPhase()` âm và các lời wait trả về trạng thái termination. Có thể override `onAdvance` cho policy khác, nhưng cần đảm bảo callbacks không tự gọi các API arrival/register/wait trên chính Phaser theo cách không được đặc tả.

### 11.4. Observer không phải party

Một observer không góp vào số parties. Nó có thể quan sát bằng:

```java
int snapshot = phaser.getPhase();
int updated = phaser.awaitAdvanceInterruptibly(
        snapshot, 2, TimeUnit.SECONDS);
```

Observer này không được gọi `arriveAndDeregister` để “dọn registration” vì nó **không đăng ký**. Nếu chỉ muốn biết một phase đã tiến mà không góp công, đây là pattern hợp lý.

## 12. Ví dụ Java 17+ hoàn chỉnh: normal, timeout, interrupt và termination

Chương trình dưới đây kiểm tra năm tình huống riêng biệt trên năm Phaser độc lập:

1. **Normal phase advance:** hai parties, một worker dùng `awaitAdvanceInterruptibly(phase,2,SECONDS)`; main đến sau, phase tiến từ 0 sang 1; cả hai deregister ở phase tiếp theo.
2. **Timeout:** tạo 2 parties, chỉ một arrival; timed wait ném `TimeoutException`; snapshot xác nhận registered=2 và unarrived=1, phase không đổi. Sau đó coordinator `forceTermination` và kiểm tra giá trị trả về âm.
3. **Interrupt:** worker đã arrive và đợi interruptibly; main gửi interrupt, worker bắt `InterruptedException` và khôi phục interrupt flag. Phase và arrivals không thay đổi.
4. **Noninterruptible:** worker dùng `awaitAdvance(phase)`; main interrupt worker rồi đến barrier. Worker vẫn trả phase 1 và giữ interrupt flag.
5. **Already advanced:** một party đã làm phase tiến trước khi gọi timed wait với timeout 0; lời chờ trả phase mới ngay, không ném timeout.

Các latches kiểm soát thứ tự trong **bài test**; chúng không được dùng như mô hình CPU workload. Code tạo threads riêng và có `Thread.join` kèm deadline; `finally` giải phóng/terminate khi cần để không để lại waiter vô hạn. Kết quả không phụ thuộc tên hay thời gian scheduling cụ thể.

Lưu thành **`PhaserInterruptibleWaitDemo.java`**:

```java
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public final class PhaserInterruptibleWaitDemo {
    static void check(boolean condition, String label) {
        if (!condition) throw new AssertionError(label);
    }

    static void joinChecked(Thread thread) throws InterruptedException {
        thread.join(3000);
        if (thread.isAlive()) {
            thread.interrupt();
            throw new AssertionError("Worker did not finish");
        }
    }

    static void normalAdvance() throws Exception {
        Phaser phaser = new Phaser(2);
        CountDownLatch ready = new CountDownLatch(1);
        AtomicInteger workerNextPhase = new AtomicInteger(-99);
        AtomicReference<Throwable> failure = new AtomicReference<>();
        Thread worker = new Thread(() -> {
            int phase = phaser.arrive();
            ready.countDown();
            try {
                workerNextPhase.set(phaser.awaitAdvanceInterruptibly(
                        phase, 2, TimeUnit.SECONDS));
                phaser.arriveAndDeregister();
            } catch (Throwable t) {
                failure.set(t);
                phaser.forceTermination();
            }
        }, "phase-normal");
        worker.start();
        try {
            check(ready.await(2, TimeUnit.SECONDS), "worker not ready");
            int next = phaser.arriveAndAwaitAdvance();
            phaser.arriveAndDeregister();
            joinChecked(worker);
            check(failure.get() == null, "worker failed: " + failure.get());
            check(next == 1 && workerNextPhase.get() == 1,
                    "unexpected phase");
            check(phaser.getRegisteredParties() == 0
                    && phaser.isTerminated(), "cleanup");
            System.out.println("normal.nextPhase=" + next);
            System.out.println("normal.workerNextPhase="
                    + workerNextPhase.get());
            System.out.println("normal.allDeregistered=true");
        } finally {
            phaser.forceTermination();
            worker.interrupt();
            joinChecked(worker);
        }
    }

    static void timedWait() throws Exception {
        Phaser phaser = new Phaser(2);
        int phase = phaser.arrive();
        boolean timedOut = false;
        try {
            phaser.awaitAdvanceInterruptibly(
                    phase, 80, TimeUnit.MILLISECONDS);
        } catch (TimeoutException expected) {
            timedOut = true;
        }
        check(timedOut, "expected timeout");
        check(phaser.getPhase() == 0, "phase changed on timeout");
        check(phaser.getRegisteredParties() == 2,
                "parties changed on timeout");
        check(phaser.getUnarrivedParties() == 1,
                "arrival changed on timeout");
        System.out.println("timeout.caught=" + timedOut);
        System.out.println("timeout.phaseUnchanged=true");
        System.out.println("timeout.registered="
                + phaser.getRegisteredParties());
        System.out.println("timeout.unarrived="
                + phaser.getUnarrivedParties());
        phaser.forceTermination();
        int result = phaser.awaitAdvanceInterruptibly(
                phase, 1, TimeUnit.SECONDS);
        check(phaser.isTerminated() && result < 0, "termination");
        check(phaser.getRegisteredParties() == 2,
                "forceTermination changed registration");
        System.out.println("timeout.forceTerminated=true");
        System.out.println("timeout.waitReturnsNegative=true");
    }

    static void interruptedWait() throws Exception {
        Phaser phaser = new Phaser(2);
        CountDownLatch ready = new CountDownLatch(1);
        AtomicBoolean caught = new AtomicBoolean();
        AtomicBoolean clearedInCatch = new AtomicBoolean();
        AtomicBoolean restored = new AtomicBoolean();
        AtomicReference<Throwable> failure = new AtomicReference<>();

        Thread worker = new Thread(() -> {
            int phase = phaser.arrive();
            ready.countDown();
            try {
                phaser.awaitAdvanceInterruptibly(phase);
                failure.set(new AssertionError(
                        "Wait should have been interrupted"));
            } catch (InterruptedException expected) {
                caught.set(true);
                clearedInCatch.set(!Thread.currentThread().isInterrupted());
                Thread.currentThread().interrupt();
                restored.set(Thread.currentThread().isInterrupted());
            } catch (Throwable t) {
                failure.set(t);
            }
        }, "phase-interrupt");

        worker.start();
        try {
            check(ready.await(2, TimeUnit.SECONDS), "worker not ready");
            worker.interrupt();
            joinChecked(worker);
            check(failure.get() == null, "unexpected worker error");
            check(caught.get() && clearedInCatch.get() && restored.get(),
                    "wrong interrupt behavior");
            check(phaser.getPhase() == 0
                    && phaser.getUnarrivedParties() == 1
                    && phaser.getRegisteredParties() == 2,
                    "interrupt unexpectedly changed phaser");
            System.out.println("interrupt.caught=true");
            System.out.println("interrupt.clearedInCatch=true");
            System.out.println("interrupt.flagRestored=true");
            System.out.println("interrupt.phaseUnchanged=true");
            System.out.println("interrupt.unarrived=1");
        } finally {
            phaser.forceTermination();
            worker.interrupt();
            joinChecked(worker);
        }
    }

    static void uninterruptibleWait() throws Exception {
        Phaser phaser = new Phaser(2);
        CountDownLatch ready = new CountDownLatch(1);
        AtomicInteger phaseAfter = new AtomicInteger(-99);
        AtomicBoolean preserved = new AtomicBoolean();
        AtomicReference<Throwable> failure = new AtomicReference<>();

        Thread worker = new Thread(() -> {
            try {
                int phase = phaser.arrive();
                ready.countDown();
                phaseAfter.set(phaser.awaitAdvance(phase));
                preserved.set(Thread.currentThread().isInterrupted());
                phaser.arriveAndDeregister();
            } catch (Throwable t) {
                failure.set(t);
                phaser.forceTermination();
            }
        }, "phase-uninterruptible");

        worker.start();
        try {
            check(ready.await(2, TimeUnit.SECONDS), "worker not ready");
            worker.interrupt();
            int next = phaser.arriveAndAwaitAdvance();
            phaser.arriveAndDeregister();
            joinChecked(worker);
            check(failure.get() == null, "worker error");
            check(next == 1 && phaseAfter.get() == 1
                    && preserved.get(), "uninterruptible semantics");
            System.out.println("uninterruptible.nextPhase=1");
            System.out.println(
                    "uninterruptible.interruptFlagPreserved=true");
        } finally {
            phaser.forceTermination();
            worker.interrupt();
            joinChecked(worker);
        }
    }

    static void alreadyAdvanced() throws Exception {
        Phaser phaser = new Phaser(1);
        int old = phaser.getPhase();
        phaser.arrive();
        int next = phaser.awaitAdvanceInterruptibly(
                old, 0, TimeUnit.NANOSECONDS);
        check(next == 1, "must return current phase immediately");
        phaser.arriveAndDeregister();
        check(phaser.isTerminated(), "deregister must terminate");
        System.out.println("advanced.immediatePhase=" + next);
        System.out.println("advanced.terminated=true");
    }

    public static void main(String[] args) throws Exception {
        normalAdvance();
        timedWait();
        interruptedWait();
        uninterruptibleWait();
        alreadyAdvanced();
        System.out.println("checks=PASS");
    }
}
```

Biên dịch và chạy trên máy có JDK 17+:

```bash
javac -encoding UTF-8 PhaserInterruptibleWaitDemo.java
java PhaserInterruptibleWaitDemo
```

**Stdout chính xác của lần chạy đã kiểm chứng:**

```text
normal.nextPhase=1
normal.workerNextPhase=1
normal.allDeregistered=true
timeout.caught=true
timeout.phaseUnchanged=true
timeout.registered=2
timeout.unarrived=1
timeout.forceTerminated=true
timeout.waitReturnsNegative=true
interrupt.caught=true
interrupt.clearedInCatch=true
interrupt.flagRestored=true
interrupt.phaseUnchanged=true
interrupt.unarrived=1
uninterruptible.nextPhase=1
uninterruptible.interruptFlagPreserved=true
advanced.immediatePhase=1
advanced.terminated=true
checks=PASS
```

### 12.1. Giải thích nhóm `normal.*`

Worker `arrive()` cho phase 0 rồi `awaitAdvanceInterruptibly(0,2,SECONDS)`. Main cũng đến, làm phase chuyển sang 1. Worker nhìn thấy phase 1; cả hai gọi `arriveAndDeregister()` **ở phase 1**, không tạo double-arrival ở phase 0. Khi không còn registered parties, default Phaser terminated. Vì vậy `normal.allDeregistered=true`.

### 12.2. Giải thích nhóm `timeout.*`

`Phaser(2)` ban đầu có 2 unarrived parties. Gọi một `arrive()` để còn 1 unarrived, nhưng không bao giờ gọi arrival thứ hai. Timed wait bắt buộc ném `TimeoutException` sau deadline demo 80 ms; state vẫn phase 0, registered=2 và unarrived=1. Sau `forceTermination`, lời chờ ngay lập tức trả số âm. **Số registered vẫn là 2** vì forceTermination không tự deregister.

### 12.3. Giải thích nhóm `interrupt.*`

Worker đã arrive trước khi main gọi `interrupt()`. `awaitAdvanceInterruptibly(phase)` ném `InterruptedException` và không đổi phase/arrivals. Khi bắt exception, interrupted flag đã được clear; worker gọi `Thread.currentThread().interrupt()` để restore. Vì thế output ghi `interrupt.clearedInCatch=true` và `interrupt.flagRestored=true`.

Không có party thứ hai đến trong scenario này. Demo `forceTermination` trong finally để cleanup thay vì để barrier chờ mãi.

### 12.4. Giải thích nhóm `uninterruptible.*`

Worker gọi `awaitAdvance(phase)`, main gửi interrupt rồi thực hiện arrival còn thiếu để phase tiến. Worker **không ném InterruptedException**, thấy phase 1 và giữ cờ interrupted. Đây là khác biệt với overload interruptible, không có nghĩa signal interrupt bị “hủy bỏ hoàn toàn”.

### 12.5. Giải thích nhóm `advanced.*`

Phaser chỉ có một party, `phaser.arrive()` làm phase tiến ngay từ 0 sang 1. Sau đó timed wait với `old=0`, timeout=0 vẫn trả **phase 1** tức thì. Caller deregister **ở phase 1** nên Phaser kết thúc bình thường.

### 12.6. Điều gì được kiểm chứng và điều gì không?

Đã kiểm chứng chương trình Java 17+ **biên dịch và chạy thành công** trên một JDK thật. Demo không có I/O, không cần network, không sửa dữ liệu của người dùng, không dựa vào thread sleep. Nó không chứng minh mọi scheduling/OS đều nhanh như nhau; deadlines có thể cần tăng cho môi trường CI chậm hoặc bị tắc CPU. Sự khác biệt về semantics bắt nguồn từ Javadoc, không từ benchmark.

## 13. Quy trình xử lý lỗi, hủy và kết thúc có chủ sở hữu

Phaser có thể được dùng trong một service nhiều đợt xử lý. Cần policy khi một party bị ngắt hoặc hết thời gian chờ:

```text
Party thực hiện phần việc phase N
             |
        phase = arrive()
             |
    awaitAdvanceInterruptibly(phase, deadline)
             |
       +-----+----------------------+------------------+
       |                            |                  |
  phase changed               Interrupted          Timed out
       |                            |                  |
 Check negative?                restore flag       log deadline
   |         |                       |                  |
 <0       >=0                  notify coordinator  notify coordinator
   |         |                       |                  |
 terminated  next phase        stop/cancel policy  retry/abort policy
       |
 coordinator determines if job aborts
       |
 notify other work + forceTermination if appropriate
       |
 confirm worker bodies/resources quiescent
       |
 close owned resources, report failure
```

**Không forceTerminate một Phaser được các request khác chia sẻ nếu chỉ có một request hết deadline riêng.** Coordinator quyết định tác động toàn hệ. Trong các job biệt lập, nếu một participant không thể tiếp tục, forceTermination có thể là lựa chọn đúng để tránh các parties khác chờ mãi.

### 13.1. Không tự động retry cùng phase sau timeout

Nếu đã `arrive()` trong phase N rồi timed out, retry một lệnh **wait** với cùng phase có thể hợp lệ khi policy cho phép, vì wait không thêm arrival. Nhưng không gọi `arrive()` một lần nữa. Nếu toàn job đã abort, phải terminate và khởi tạo vòng đời mới rõ ràng.

### 13.2. Không double deregister

`arriveAndDeregister()` vừa arrival vừa bỏ registration; nếu called twice theo cùng protocol hoặc sau `arrive()` cùng phase sẽ làm sai bộ đếm. Code dùng `finally` phải biết party đang ở phase nào và đã arrive chưa, không gọi deregister vô điều kiện.

### 13.3. Chờ thread rời Phaser khác với dừng body

`forceTermination` đánh thức các **Phaser waits**. Nó không interrupt một thread đang bận CPU, chờ I/O khác hoặc lock khác. Muốn job thật sự dừng, có thể dùng cooperative cancellation flag, đóng tài nguyên do job sở hữu hoặc truyền signal phù hợp rồi **join/await** các worker bodies.

### 13.4. Cleanup sau InterruptedException

Nếu một thread nhận `InterruptedException`, code cần đưa ra quyết định:
- Nếu dừng: restore interrupt flag, báo coordinator, chuyển sang cleanup.
- Nếu policy chủ động bỏ qua và tiếp tục: chỉ làm khi được thiết kế rõ, không nuốt tín hiệu vô hạn.
- Nếu đang giữ resource: tránh đóng trước khi các workers khác hết dùng resource ấy.

## 14. Các lỗi phổ biến và cách sửa

| Sai lầm | Vì sao sai | Cách đúng |
| --- | --- | --- |
| Dùng `arriveAndAwaitAdvance()` rồi mong ném `InterruptedException` | Method này không interruptible | Tách `arrive` + `awaitAdvanceInterruptibly` |
| Mong `arriveAndAwaitAdvance(timeout)` tồn tại | Không có overload này | Dùng timed `awaitAdvanceInterruptibly` |
| Gọi `awaitAdvanceInterruptibly` mà không arrival dù là party | Barrier còn đợi arrival của chính mình | `arrive` trước rồi dùng returned phase |
| Observer tự gọi `arrive` | Làm sai số parties | Observer chỉ `getPhase` + wait |
| Gọi `arrive` hai lần trong cùng phase | Double-arrival, sai bộ đếm | Một arrival / một party / một phase |
| Timeout rồi gọi `arriveAndDeregister` ngay sau `arrive` | Deregister cũng ghi arrival | Chọn phục hồi coordinator hoặc deregister phase tiếp theo |
| Nghĩ `TimeoutException` tự deregister | Không thay đổi Phaser state | Xây dựng recovery policy riêng |
| Nghĩ `InterruptedException` forceTerminate Phaser | Không tự terminate | Owner quyết định `forceTermination` |
| Nuốt `InterruptedException` | Mất yêu cầu dừng, chờ mãi | Restore flag, propagate/cleanup |
| Không kiểm tra `nextPhase<0` | Termination bị hiểu là success | Xử lý trạng thái âm |
| Chỉ xét `timeout=0` để đoán kết quả | Phase có thể đã tiến | So sánh phase hiện tại và argument |
| Gọi `forceTermination` trong một helper dùng chung | Dừng cả Phaser được nhiều parties dùng | Chỉ owner/coordinator quyết định |
| Nghĩ `forceTermination` giảm registered parties về 0 | Contract nói counts không đổi | Không dùng counts sau terminate làm cleanup signal |
| Nghĩ `forceTermination` ngừng CPU task | Chỉ đánh thức Phaser waits | Cooperative stop/worker join |
| Tạo party nhưng quên arrival | Các bên khác có thể treo | Đăng ký đúng thời điểm, đảm bảo arrival/cancel policy |
| Dựa `getUnarrivedParties` để thực thi protocol sau terminated | Snapshot vô nghĩa sau terminate | Dùng `isTerminated` và trạng thái nghiệp vụ |
| Hard-code phase luôn tăng đúng 1 | Có thể race/nhiều phase hoặc wraparound | So sánh đúng với phase đã quan sát |
| Gọi `register` vào Phaser terminated rồi mong tái dùng | Register không cứu một terminated phaser | Tạo Phaser mới cho lifecycle mới |
| Dùng `Thread.sleep` để test interrupt | Test flaky | Latches, deadlines và signals |
| Để worker chờ trong pool quá nhỏ | Có thể starvation nếu workers chờ nhau | Kiểm soát số blocked parties và pool parallelism |

## 15. Ma trận kiểm thử tối thiểu

| Test | Cấu hình | Assertion |
| --- | --- | --- |
| Phase bình thường | 2 parties, đủ arrivals | `awaitAdvanceInterruptibly` trả phase mới |
| Worker bị interrupt | 2 parties, còn 1 unarrived | `InterruptedException` và phase không đổi |
| Timed wait hết hạn | 2 parties, chỉ 1 arrival | `TimeoutException`, party counts không đổi |
| Force termination | Party cuối không đến | `isTerminated=true`, next wait trả số âm |
| Không interruptible | `awaitAdvance` + `interrupt` | Vẫn chờ phase tiến, flag preserved |
| Phase cũ | Một party đã làm advance | Timed await trả ngay dù timeout 0 |
| Party đăng ký rồi bỏ quên arrival | Không có coordinator recovery | Barrier có nguy cơ treo |
| Observer wait | Không register/arrive | Không làm thay đổi registered/arrived |
| Double arrival cùng phase | Caller gọi hai arrival methods | Phải chặn bằng protocol, không thử trên shared data |
| Deregistration bình thường | Mỗi party rời ở phase hợp lệ | Registered parties về 0, default termination |
| Overlapping interrupt/timeout | Hai sự kiện sát nhau | Test chấp nhận race nếu không có sequencing |
| Shared Phaser | Một party timeout | Chỉ coordinator áp dụng global abort |

Các phép thử dùng **latches có deadline**, `Thread.join` hoặc một bộ đếm phase đã kiểm chứng. Không viết test phụ thuộc “worker luôn chạy sau 50 ms”.

## 16. FAQ

**1. `awaitAdvanceInterruptibly` có tự gọi `arrive()` không?**  
Không. Nó chỉ đợi một phase khác với `phase` đã truyền. Nếu caller là registered party, thường phải `arrive()` một lần trước khi chờ.

**2. Tại sao phải truyền `phase` từ `arrive()`?**  
Giá trị ấy là phase vừa được ghi nhận arrival, tránh đợi sai phase khi những threads khác tiến barrier đồng thời.

**3. `awaitAdvanceInterruptibly(phase)` có timeout không?**  
Không. Dùng overload nhận `long timeout, TimeUnit unit` khi cần deadline.

**4. `awaitAdvanceInterruptibly(phase, timeout, unit)` trả boolean thành công?**  
Không. Nó trả **int phase**, hoặc ném checked exception; số âm báo termination.

**5. Khi thread bị interrupt, Phaser có auto-terminate không?**  
Không. `InterruptedException` không đổi trạng thái Phaser.

**6. Timeout có tự giảm số parties không?**  
Không. Registration và arrival counts giữ nguyên trừ khi có hoạt động từ các parties khác.

**7. Tôi đã `arrive()`, sau timeout có nên `arriveAndDeregister()` ngay không?**  
Không nếu vẫn cùng phase: nó gây double-arrival. Dùng policy coordinator, force termination nếu abort toàn đợt, hoặc deregister ở phase sau.

**8. `awaitAdvance(phase)` có ném InterruptedException không?**  
Không. Theo tài liệu, nó tiếp tục chờ dù thread bị interrupt.

**9. `arriveAndAwaitAdvance()` có thể dùng cho barrier có hạn chờ?**  
Không trực tiếp. Tách `arrive` và timed `awaitAdvanceInterruptibly`.

**10. Nếu phase đã đổi trước khi tôi gọi timed wait thì sao?**  
Method trả phase mới ngay, kể cả cấu hình timeout=0.

**11. `forceTermination` có ngắt worker threads không?**  
Không. Nó kết thúc Phaser và giải phóng Phaser waits; application phải quản lý worker cancellation riêng.

**12. Có thể gọi `register` trên terminated Phaser để mở lại không?**  
Không. Tạo Phaser mới nếu cần một lifecycle khác.

**13. `getPhase() < 0` nghĩa là gì?**  
Phaser terminated. Không hiểu số âm như một phase thành công bình thường.

**14. Tại sao test dùng CountDownLatch nếu đang học Phaser?**  
Latches chỉ điều khiển thời điểm của bài test để kiểm chứng interrupt/timeout ổn định; đối tượng cần học vẫn là `Phaser.awaitAdvanceInterruptibly`.

**15. Một observer có thể dùng timed wait mà không đăng ký party không?**  
Có. Observer lấy snapshot `getPhase` rồi chờ thay đổi; không tự gọi arrival/deregister.

**16. Nếu chỉ một party timeout trong hệ thống dùng chung, có được forceTerminate không?**  
Chỉ khi coordinator/owner của toàn hệ thống quyết định. Một helper không nên dừng mọi parties vì timeout riêng.

## 17. Checklist code review

- [ ] Xác định Phaser do scope nào sở hữu và ai được forceTerminate.
- [ ] Registered parties đúng số lượng và đăng ký trước khi chúng cần được đợi.
- [ ] Phân biệt `arrive` với `awaitAdvance`.
- [ ] Nếu muốn interruptible wait, dùng `awaitAdvanceInterruptibly`.
- [ ] Nếu muốn deadline, dùng đúng overload có `timeout` và `TimeUnit`.
- [ ] Dùng arrival phase trả về từ `arrive()` nếu caller là party.
- [ ] Không double-arrive trong cùng phase.
- [ ] Không gọi `arriveAndDeregister` sau một `arrive` cùng phase.
- [ ] Catch `InterruptedException`, restore flag và áp dụng cleanup policy.
- [ ] Catch `TimeoutException` và thông báo coordinator.
- [ ] Không coi timeout/interrupt là đã tự deregister hay terminate.
- [ ] Khi return từ await, kiểm tra số âm/`isTerminated`.
- [ ] Không coi snapshot `getUnarrivedParties` có ý nghĩa sau termination.
- [ ] Không nhầm interrupt của thread chờ với interrupt/cancel tất cả tasks.
- [ ] Không làm global `forceTermination` từ component không sở hữu Phaser.
- [ ] Nếu abort, đánh thức waiters và yêu cầu worker bodies dừng riêng.
- [ ] Chờ quiescence trước khi đóng tài nguyên shared.
- [ ] Không block trong pool quá nhỏ khiến các parties không thể progress.
- [ ] Test normal, timeout, interrupt, noninterruptible, already advanced và termination.
- [ ] Tests có deadline, không dựa vào timing `Thread.sleep`.
- [ ] Java code/stdout đã biên dịch và kiểm tra trên JDK phù hợp.

## 18. Kết luận và tài liệu chính thức

Với **Phaser – Chờ có thể ngắt hoặc hết thời hạn**, cách dùng an toàn trong Java 17+ là:

1. Party đã hoàn thành phần việc của phase hiện tại gọi **`arrive()` đúng một lần**.
2. Lấy phase trả về để dùng với `awaitAdvanceInterruptibly(phase)` hoặc `awaitAdvanceInterruptibly(phase, timeout, TimeUnit)`.
3. Phân loại riêng **phase tiến bình thường**, **phaser terminated**, **InterruptedException** và **TimeoutException**.
4. Nhớ rằng exception khi đợi **không thay đổi số parties hay arrival counts**.
5. Nếu phải abort, coordinator có thể `forceTermination`, đồng thời quản lý cancellation và cleanup của những công việc thực tế.
6. Không deregister hoặc arrive lần hai trong cùng phase; không giải phóng shared resource trước khi các worker bodies kết thúc an toàn.

Đây là API từ Java 7 vẫn có giá trị và được duy trì trong Java 17+.

### Tài liệu chính thức Java SE 17

- [Oracle `Phaser`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Phaser.html): phase, arrival/wait separation, interruptible/timed waits, termination và party lifecycle.
- [Oracle `InterruptedException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/InterruptedException.html): tín hiệu thread bị interrupt khi đang chờ.
- [Oracle `TimeoutException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/TimeoutException.html): checked exception khi một operation timed out.
- [Oracle `TimeUnit`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/TimeUnit.html): units cho timeout và duration conversion.
- [Oracle `CountDownLatch`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): kiểm thử điều phối timing giữa threads.
- [Oracle `ForkJoinPool`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ForkJoinPool.html): caveat khi có nhiều parties blocked trong worker pool.
