# Điều kiện kết thúc và tùy biến `onAdvance` trong Java `Phaser`

## 1. Tại sao Phaser cần điều kiện kết thúc?

`java.util.concurrent.Phaser` là một rào chắn đồng bộ (**reusable synchronization barrier**) cho nhiều đợt công việc: các bên (**parties**) đăng ký, hoàn thành phần việc của một **phase**, báo đã đến, rồi đợi các bên khác trước khi chuyển sang phase tiếp theo. Khác một rào chắn chỉ dùng một lần, `Phaser` có thể được sử dụng qua nhiều vòng và có thể đăng ký/rút parties động.

Nhưng không phải mọi quy trình đều cần chạy mãi. Có quy trình phải dừng sau **N vòng**; có quy trình dừng khi **không còn party**; có quy trình phải **hủy ngay khi một worker gặp lỗi**. Java cho hai cơ chế quan trọng:

1. **Kết thúc khi chuẩn bị chuyển phase:** override `protected boolean onAdvance(int phase, int registeredParties)`. Nếu trả `true`, phaser chuyển sang trạng thái terminated; nếu trả `false`, nó tiếp tục sang phase kế tiếp.
2. **Kết thúc cưỡng bức bất cứ lúc nào:** `forceTermination()`, thường dùng trong xử lý lỗi/hủy để giải phóng các bên đang chờ.

Phân biệt hai cơ chế rất quan trọng: `onAdvance` là **hook tại ranh giới phase**, không chạy ở mọi lời gọi arrival; còn `forceTermination` là **đường hủy không cần đợi đầy đủ arrivals**.

**Chủ đề trực tiếp:** “Điều kiện kết thúc và tùy biến onAdvance”, nhóm cha “Phaser”.

**Tính hiện hành / Special Note:** `Phaser`, `onAdvance`, `isTerminated` và `forceTermination` đều có từ Java 7, **vẫn là Java SE API hiện hành trên Java 17, 21 và JDK mới**. Mã thực hành dùng Java 21, không dùng API lỗi thời hoặc legacy. Những khuyến nghị về lỗi, deadline, dữ liệu và quản lý thread phản ánh cách dùng còn áp dụng hiện nay.

### Sau bài học, bạn cần nắm

- Tại sao implementation mặc định của `onAdvance` kết thúc khi một lượt `arriveAndDeregister` làm số registered parties về 0.
- Thời điểm hook được gọi, ý nghĩa hai tham số và ý nghĩa `true`/`false`.
- Cách kết thúc sau đúng một số vòng (tránh lỗi `off-by-one`).
- Cách **không kết thúc khi về 0 party**, để cho phép `register` lại sau này.
- Cách dùng `isTerminated()`, `getPhase()` âm và các giá trị trả về của `arrive`/`awaitAdvance`.
- Cách giải phóng waiters khi lỗi bằng `forceTermination()`, và các việc **nó không làm**.
- Các giới hạn quan trọng của hook: không gọi `register`, `arrive` hoặc phương thức chờ trên cùng phaser bên trong hook; không block lâu; không ném ngoại lệ không kiểm soát.
- Cách xử lý nhiều threads, rút parties, callback, tiered phasers, timeout, recovery và dọn executor theo ownership.
- Kiểm thử bằng chương trình Java 21 có cả termination mặc định, custom fixed rounds, giữ sống khi registered=0, abort và hook thất bại.

## 2. Trước khi bàn termination: vòng đời một phase

Một phaser giữ các số liệu:

| API | Ý nghĩa |
| --- | --- |
| `getPhase()` | Số hiệu phase hiện tại, bắt đầu từ 0, tăng sau các lần advance thành công; **âm khi terminated** |
| `getRegisteredParties()` | Tổng số parties vẫn đăng ký tại phaser này |
| `getArrivedParties()` | Số registered parties đã báo arrival trong phase hiện tại |
| `getUnarrivedParties()` | Số registered parties chưa arrival trong phase hiện tại |
| `isTerminated()` | Kiểm tra trạng thái kết thúc |

Một trạng thái chưa bị thay đổi đồng thời thường có quan hệ:

\[
\text{registered}=\text{arrived}+\text{unarrived}.
\]

Các getters **không tạo một snapshot nguyên tử chung**; nếu nhiều threads cập nhật đúng lúc đọc, có thể đọc nhiều phase khác nhau. Chúng chủ yếu dành cho monitoring, không phải thay thế `arriveAndAwaitAdvance` hoặc `awaitAdvance`.

Ví dụ `new Phaser(2)` có trạng thái ban đầu:

~~~text
phase = 0
registered = 2
arrived = 0
unarrived = 2

Party A arrive() => arrived=1, unarrived=1, phase=0
Party B arrive() => lượt cuối, chạy onAdvance(0, 2)
                     nếu onAdvance trả false:
                       phase=1, arrived=0, unarrived=2
                     nếu onAdvance trả true:
                       trạng thái terminated, phase âm
~~~

*Đây là luồng khái niệm*, giả định hai parties vẫn đăng ký trong phase 0. Nếu một party rút đăng ký trong lúc arrival thì tham số `registeredParties` phản ánh trạng thái đang chuyển ngay thời điểm hook được gọi.

### 2.1. Party không phải ID của thread

`Phaser` quản lý số lượng **parties logic**, không giữ danh sách xác thực thread hay task ID. Nếu tạo `Phaser(2)`, ứng dụng phải tổ chức để **đúng hai registered parties** arrival mỗi phase. Các lời gọi arrival/deregistration từ một party chưa đăng ký hoặc arrival hai lần một phase là lỗi dùng API, dù nó có thể không bị phát hiện ở đúng lời gọi gây lỗi.

### 2.2. Một phase advance khác với một task hoàn tất

Một party gọi `arrive()` nghĩa là nó đã đến barrier của phase đó. Nếu công việc nghiệp vụ còn I/O, transaction, response chưa thực sự hoàn tất nhưng code đã arrival sớm, phaser có thể advance **trước khi business work xong**. Hook chỉ biết tình trạng arrival, không xác nhận tất cả external systems đã commit.

## 3. `onAdvance(int phase, int registeredParties)` chính xác là gì?

Chữ ký API:

~~~java
protected boolean onAdvance(int phase, int registeredParties)
~~~

Phương thức thuộc lớp `Phaser` và **được thiết kế để override** trong subclass hoặc anonymous subclass. Nó được gọi khi **bên cuối của một phase đến**, tức thời điểm chuẩn bị chuyển phase.

- `phase`: số hiệu **phase sắp hoàn tất**, trước khi advance; không phải số của phase mới.
- `registeredParties`: số registered parties ở thời điểm chuyển phase, đã bao gồm ảnh hưởng của những lượt deregistration trước đó.
- Trả `false`: cho phép đi tiếp tới phase sau.
- Trả `true`: chuyển phaser sang trạng thái **terminated**.
- Hook chạy trong thread của **party kích hoạt phase advance**, không phải một thread watcher được tạo tự động.
- Khi có tiered phasers, hook được gọi trên **root phaser** cho mỗi lượt advance của cây; không giả định hook của mọi child đều chạy.
- Nếu hook ném unchecked exception hoặc `Error`, nó được **truyền lên party kích hoạt advance**, và **không xảy ra phase advance** theo Javadoc; phải có recovery policy.

### 3.1. Phân biệt phase đang kết thúc và phase tiếp theo

Một ví dụ muốn chạy **ba** vòng có các phase xử lý 0, 1, 2. Hook được gọi:

~~~text
onAdvance(phase=0, registered=R) -> false -> cho phép phase 1
onAdvance(phase=1, registered=R) -> false -> cho phép phase 2
onAdvance(phase=2, registered=R) -> true  -> TERMINATED
~~~

Điều kiện đúng là:

~~~java
return phase >= rounds - 1 || registeredParties == 0;
~~~

khi `rounds` là số dương, phase bắt đầu ở 0, và nghiệp vụ muốn kết thúc ở ranh giới của vòng cuối. Nếu nhầm viết `phase >= rounds` thì quy trình có thể chạy **thêm một phase**, vì phase argument là số phase đang hoàn tất chứ không phải số phase kế tiếp.

### 3.2. Vì sao không làm công việc chặn lâu trong hook?

Lượt arrival cuối cùng phải chạy `onAdvance` để hoàn tất chuyển phase, nên các bên khác có thể **tiếp tục chờ** cho tới khi hook xong. Nếu hook gọi HTTP, chờ database, `Thread.sleep` lâu, hoặc đợi một task chỉ có thể chạy **sau phase advance**, cả nhóm bị kẹt.

Nên giữ hook **nhanh, không chặn**: kiểm tra một điều kiện dừng, cập nhật một biến/metric đơn giản với synchronization phù hợp hoặc phát tín hiệu an toàn. Những bước business nặng nên được thiết kế **trước khi arrival** hoặc chuyển sang executor khác với lifecycle rõ ràng, không buộc hook đợi việc phụ thuộc vào advance.

### 3.3. Không gọi những phương thức Phaser nào từ trong hook?

Javadoc Java SE 21 nêu rằng tác động của việc gọi các phương thức **arrival, registration hoặc waiting trên cùng phaser** bên trong `onAdvance` là **không được đặc tả**. Vì vậy không viết:

~~~java
@Override
protected boolean onAdvance(int phase, int parties) {
    register();                // Không an toàn trong onAdvance.
    arriveAndAwaitAdvance();   // Không an toàn; có thể tự kẹt.
    return false;
}
~~~

Đây là **phản ví dụ**, không phải code để chạy. Tương tự, đừng làm `awaitAdvance(phase)` bên trong hook, vì hook đang giữ chính sự kiện cần xảy ra để lời chờ hoàn tất. Muốn thay đổi số parties, tổ chức `register/deregister` bên ngoài hook, có coordination với phase boundaries.

## 4. Điều kiện kết thúc mặc định: hết registered parties

Implementation mặc định của `Phaser.onAdvance` trả `true` **khi lượt deregistration làm số registered parties về 0**. Đây là một mặc định hợp lý: khi không còn ai tham gia, barrier không cần duy trì các phase nữa.

~~~java
Phaser phaser = new Phaser(1);
int arrivedAtPhase = phaser.arriveAndDeregister();
boolean done = phaser.isTerminated();
~~~

Đây là đoạn minh họa (cần `import java.util.concurrent.Phaser;`). Với phaser mới có một party và không có hoạt động đồng thời:

- Trước thao tác: phase 0, registered 1, unarrived 1.
- `arriveAndDeregister()` ghi nhận arrival và giảm registered xuống 0.
- Vì đây cũng là arrival cuối, hook mặc định được gọi và trả true.
- `isTerminated() == true` và `getPhase() < 0`.
- `arrivedAtPhase == 0`, vì `arriveAndDeregister()` trả **phase của lượt arrival**, không phải phase âm sau termination.

### 4.1. Vì sao `new Phaser()` không tự terminated ngay?

~~~java
Phaser phaser = new Phaser(); // 0 parties, phase = 0, chưa terminated.
int p = phaser.register();   // Đăng ký một party, nếu chưa terminated.
~~~

Constructor với 0 parties **không phải** một lượt `arriveAndDeregister()`, nên không kích hoạt mặc định `onAdvance`. Bạn có thể đăng ký thêm parties sau khi tạo. Không đánh đồng `getRegisteredParties()==0` với `isTerminated()==true` trong mọi trường hợp.

### 4.2. Nếu vẫn còn party thì không tự kết thúc

Giả sử phaser ban đầu có ba parties, một party `arriveAndDeregister`, hai parties còn lại arrival đủ để advance. Khi hook mặc định thấy `registeredParties==2`, nó trả false và phaser sang vòng mới. Nó chỉ tự terminated khi kết quả của deregistration cuối cùng khiến số registered về 0 tại ranh giới phase.

### 4.3. Nếu một party làm việc xong, dùng API nào?

- Còn tham gia vòng sau: `arrive()` hoặc `arriveAndAwaitAdvance()` theo nhu cầu chờ.
- Không tham gia vòng sau: `arriveAndDeregister()`.
- Chỉ quan sát phase mà **không** là registered party: `awaitAdvance(phase)`, không gọi arrival.
- Có lỗi/hủy cần giải phóng cả nhóm: phối hợp `forceTermination()` và cleanup, không chỉ để một party biến mất.

**Một party không nên gọi `arrive()` rồi lại `arriveAndDeregister()` trong cùng phase**, vì đó là double arrival cho một registration; không dùng deregistration như một lệnh “gỡ bất kỳ lúc nào” tách hoàn toàn khỏi arrival.

## 5. Tùy biến kết thúc sau N vòng bằng subclass

Muốn toàn bộ nhóm làm đúng **N phase hoàn chỉnh**, tạo subclass của `Phaser` và override `onAdvance`:

~~~java
final class FixedRoundsPhaser extends Phaser {
    private final int rounds;

    FixedRoundsPhaser(int parties, int rounds) {
        super(parties);
        if (rounds <= 0) {
            throw new IllegalArgumentException("rounds must be positive");
        }
        this.rounds = rounds;
    }

    @Override
    protected boolean onAdvance(int phase, int registeredParties) {
        return registeredParties == 0 || phase >= rounds - 1;
    }
}
~~~

Đây là **mã minh họa standalone class** cho logic hook (cần import `Phaser`). Lớp `FixedRoundsPhaser` trong chương trình chạy phần 9 còn thu thập log các transitions để dễ kiểm thử.

### 5.1. Tại sao cần kiểm tra `registeredParties == 0`?

Nếu mọi party rút sớm và không còn ai ở barrier, điều kiện `registeredParties == 0` cho phép phaser kết thúc thay vì sống ở trạng thái không còn bên tham gia. Đây là chính sách **giữ hành vi mặc định** đồng thời thêm giới hạn số vòng. Nếu nghiệp vụ cố tình muốn duy trì phaser khi có 0 parties, xem phần 6.

### 5.2. Ý nghĩa `rounds - 1`

- `rounds=1` → khi phase 0 hoàn tất, trả true, dừng sau một vòng.
- `rounds=2` → phase 0 trả false, phase 1 trả true.
- `rounds=3` → phase 0,1 trả false; phase 2 trả true.
- `rounds=5` → các phase 0..3 trả false; phase 4 trả true.

Đây là ví dụ với vòng đời ngắn, chưa xét việc phase number có thể wrap từ `Integer.MAX_VALUE` về 0 khi chạy cực lâu. Với số vòng lớn hơn phạm vi phase, dùng một counter/điều kiện nghiệp vụ khác được phối hợp an toàn, không giả định phase là một unique ID vô hạn.

### 5.3. Sử dụng `isTerminated()` để kết thúc vòng lặp

Cách an toàn là kiểm tra termination sau khi barrier trở về:

~~~java
while (!phaser.isTerminated()) {
    doWorkForCurrentRound();
    int result = phaser.arriveAndAwaitAdvance();
    if (phaser.isTerminated() || result < 0) {
        break;
    }
}
~~~

Đây là **mã minh họa**, `doWorkForCurrentRound()` là hàm nghiệp vụ do ứng dụng định nghĩa; từng party phải được đăng ký và có đủ khả năng tiến tới barrier. **Không chỉ dựa vào trị trả về của `arriveAndAwaitAdvance()` tại đúng lượt kích hoạt termination:** Javadoc phân biệt arrival phase và current phase âm khi terminated; code đúng cần xem **trạng thái phaser** và không xử lý thêm vòng sau termination.

Trong ví dụ chạy, hai workers mỗi người hoàn tất đúng ba lần arrival. Kết quả `getPhase()` sau termination âm; chính hook đã quan sát các transition của phase 0,1,2.

### 5.4. Tránh nhầm `onAdvance` với `onCompletion` của task

`Phaser.onAdvance` là hook của **rào chắn**, không phải callback hoàn tất của một `Future`, `CompletableFuture` hay `ForkJoinTask`. Nó chạy một lần khi **phase advance**; số lần hook chạy không nhất thiết bằng số task làm việc, cũng không biết chi tiết task nào lỗi nếu app chưa truyền trạng thái lỗi qua một cơ chế khác.

## 6. Override `onAdvance` luôn trả false: giữ Phaser khi 0 party

Có trường hợp một service cần “khởi động lại” các nhóm công việc theo từng đợt: một đợt kết thúc, không còn party; sau đó hệ thống sẽ đăng ký một nhóm mới trên **cùng phaser**. Mặc định phaser sẽ terminated nếu deregistration cuối làm registered về 0, nên bạn có thể override:

~~~java
Phaser reusable = new Phaser(1) {
    @Override
    protected boolean onAdvance(int phase, int registeredParties) {
        return false;
    }
};
~~~

Đây là một **anonymous subclass**. Trả false ngay cả khi `registeredParties==0` khiến phase advance tiếp mà **không terminated**, để có thể đăng ký lại sau đó.

~~~text
Trước rút:              phase=0 registered=1 isTerminated=false
arriveAndDeregister()
Sau rút:                phase=1 registered=0 isTerminated=false
register()              trả 1, registered=1
arriveAndDeregister()   phase=2 registered=0 isTerminated=false
forceTermination()      isTerminated=true, getPhase()<0
~~~

Kịch bản này được chương trình phần 9 kiểm thử với JDK 21. **Không có nghĩa phaser sẽ tự hoạt động khi registered=0**: nếu không ai register/arrive, không có transition mới. Bạn phải quản lý việc đăng ký đợt tiếp theo.

### 6.1. Đừng dùng `onAdvance(false)` để né cleanup

Một phaser giữ sống với 0 parties có thể hữu ích cho workflow tái sử dụng, nhưng nếu owner không còn cần nó, phải có **điểm kết thúc rõ ràng**; thông thường `forceTermination()` khi shutdown hoặc một điều kiện kết thúc khác trong hook.

Đừng giữ một phaser không terminating rồi dùng các thread daemon chờ vô hạn để mong “lúc nào đó” có party mới: việc đăng ký/arrival phải được điều phối từ một thành phần còn sống và có trách nhiệm.

### 6.2. Trạng thái 0 parties không phải failure

`getRegisteredParties()==0` có thể đồng thời với `isTerminated()==false` nếu phaser mới tạo hoặc subclass ngăn default termination. **Dùng `isTerminated()` để kiểm tra termination**, không chỉ nhìn party count. Ngược lại, sau `forceTermination()`, registered parties **không tự biến thành 0**; đừng dùng count thay thế termination flag.

## 7. `forceTermination()`: đường hủy ngay, không cần chờ mọi party

Khi một worker lỗi trước khi báo arrival, những parties khác có thể **đang chờ vĩnh viễn**. `forceTermination()` buộc phaser sang trạng thái terminated ngay lập tức và **giải phóng các waiters** theo hợp đồng API, không cần chờ tất cả parties đến.

~~~java
phaser.forceTermination();
if (phaser.isTerminated()) {
    // Không tiếp tục thực hiện công việc của phase mới.
}
~~~

Đoạn trên là **minh họa**, cần quản lý job outcomes và cleanup của hệ thống. `forceTermination` rất phù hợp làm một phần của error-recovery path.

### 7.1. Force termination không làm những việc gì?

- Không tự **interrupt hoặc kill** mọi thread/task đang làm việc.
- Không tự hủy network I/O, database transaction hoặc ghi file đang chạy.
- Không tự rollback dữ liệu mà những task đã sửa.
- **Không làm registered parties về 0**; các bộ đếm được giữ theo contract, còn arrived/unarrived sau termination không nên dùng làm số liệu tiến độ.
- Không biến phaser terminated thành phaser có thể tái sử dụng; `register()` trên một phaser đã terminated **không có hiệu lực**.
- Nếu thuộc nhóm tiered phasers, `forceTermination` làm **toàn bộ cây phasers** terminated, không chỉ một child tách biệt.
- Nếu đã terminated, gọi `forceTermination()` lần nữa không tạo thêm thay đổi mới.

Với một workflow nhiều vòng, người quản lý cần báo lỗi đầu tiên/termination reason ở một cấu trúc riêng (ví dụ `AtomicReference<Throwable>` hoặc result object) nếu cần biết **vì sao** dừng. `Phaser` chỉ biểu thị barrier state, không tự ghi một business exception/reason.

### 7.2. Ví dụ một waiter đã đến nhưng bên khác không đến

~~~text
Phaser(2): registered = 2
Worker A: arrive() -> unarrived = 1
Worker A: awaitAdvanceInterruptibly(phase, 5s) -> đang chờ
Coordinator: forceTermination() -> phaser terminated
Worker A: waiter returns negative phase
Worker B: không cần arrival để mở barrier
~~~

Đây là mô hình của phần code đầy đủ. Trong bài test, `CountDownLatch` bảo đảm coordinator chỉ gọi forceTermination **sau khi** worker đã ghi nhận `arrive()`, không dựa vào `Thread.sleep`. Dù worker thực sự vào trạng thái wait trước hay sau lực hủy, method `awaitAdvanceInterruptibly` nhận thấy phaser đã terminated và trả ngay với phase âm.

### 7.3. `awaitAdvanceInterruptibly` với timeout không tự kết thúc Phaser

~~~java
int arrivalPhase = phaser.arrive();
try {
    int next = phaser.awaitAdvanceInterruptibly(
            arrivalPhase, 5, TimeUnit.SECONDS);
    if (next < 0 || phaser.isTerminated()) {
        // Recovery: pipeline đã dừng.
    }
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    phaser.forceTermination(); // Chính sách fail-fast của ví dụ.
} catch (TimeoutException e) {
    phaser.forceTermination(); // Chủ động hủy theo policy.
}
~~~

Đây là mã minh họa, cần imports và error propagation. **Timeout/interruption của một lời chờ không tự thay đổi trạng thái Phaser** theo Javadoc; `forceTermination()` ở đây là lựa chọn **do ứng dụng chủ động thực hiện**. Phải phối hợp cancellation, cleanup và shutdown executor theo ownership.

### 7.4. `awaitAdvance` không interruptible

`awaitAdvance(phase)` không chấm dứt chờ chỉ vì thread bị interrupt; bản interruptible `awaitAdvanceInterruptibly(...)` mới đáp ứng interruption/timeout. Khi xây shutdown có deadline, chọn đúng overload và có đường `forceTermination` để các waiters không kẹt.

## 8. Ngoại lệ trong `onAdvance`: vì sao đặc biệt nguy hiểm?

Khi hook ném unchecked exception hoặc `Error`, Javadoc bảo đảm lỗi được truyền đến **party đang kích hoạt phase advance**, **và phase advance không xảy ra**. Một số parties khác có thể còn đợi phase ấy đổi.

~~~java
Phaser faulty = new Phaser(1) {
    @Override
    protected boolean onAdvance(int phase, int registeredParties) {
        throw new IllegalStateException("hook failure");
    }
};
~~~

Đây là **mã minh họa**. Nếu thread duy nhất gọi `faulty.arriveAndAwaitAdvance()`, nó nhận `IllegalStateException`, còn `faulty.getPhase()` có thể vẫn là phase 0. Trong bài demo thật, ta kiểm tra `faulty-phase-not-advanced=true`, rồi gọi `forceTermination()` trong `finally`.

**Cách thiết kế thực tế:**

1. Đảm bảo hook gọn, không gọi code ứng dụng tùy ý có thể lỗi.
2. Nếu hook cần cập nhật metadata, giới hạn logic có thể ném exception.
3. Nếu hook thực sự lỗi, **có cơ chế bắt lỗi ở boundary** của party kích hoạt advance, báo lỗi chung và `forceTermination()` để giải phóng waiters khác.
4. Không coi việc ném trong hook là cách yêu cầu termination. Để kết thúc **bình thường**, trả `true`.
5. Không tiếp tục gửi arrival vào cùng phaser đang ở trạng thái khó khôi phục như thể không có lỗi; thường terminate và tạo phaser mới sau khi khắc phục.

### 8.1. Side effect ở hook cần cẩn trọng

`onAdvance` có thể được gọi bởi worker bất kỳ là **bên đến cuối**, không có đảm bảo nó là coordinator/main. Nếu hook ghi log/metric hoặc cập nhật một `List`, cần chọn data structure và thời điểm đọc phù hợp. Trong chương trình, list transitions chỉ được hook ghi **một lần trên mỗi phase** và main chỉ đọc **sau khi Futures của workers đã hoàn tất**. Không dùng `ArrayList` đó làm bảng trạng thái live cho threads đọc song song mà thiếu synchronization.

### 8.2. Hook không phải một callback “sau khi đã advance”

`onAdvance(phase,R)` diễn ra **trước khi trạng thái phase mới được công bố**. Nó được gọi khi các parties khác đang chờ. Vì vậy code bên trong hook không được đòi “chờ tới phase tiếp theo” để rồi mới trả về, vì đó chính là sự kiện chỉ có thể hoàn tất **sau khi hook trả về**.

### 8.3. Tương tác với thread interruption

Không nên đặt lời đợi có timeout hoặc logic nhận `InterruptedException` trực tiếp trong hook như một cách điều phối với worker khác. Worker triggering advance có thể bị giữ lâu, khiến toàn bộ phaser không tiến. Nếu thực sự cần hoàn tất một bước nghiệp vụ trước khi cho các parties tới barrier, hãy tổ chức bước đó **trước khi báo arrival**.

## 9. Chương trình Java 21 hoàn chỉnh: năm tình huống termination

Để quan sát chính xác kết quả mà **không cần mạng hay dữ liệu ngoài**, chương trình `PhaserTerminationExample` sau đây kiểm tra:

1. **Mặc định:** `new Phaser(1)`, party cuối `arriveAndDeregister` → terminated, getPhase âm.
2. **Tùy biến số vòng:** `FixedRoundsPhaser(2,3)`, hai workers chạy ba phase qua `arriveAndAwaitAdvance`; hook ghi đúng các chuyển phase 0, 1, 2 và dừng.
3. **Giữ sống khi 0 party:** anonymous subclass `onAdvance` luôn false; deregister cuối → phase 1 nhưng **không** terminated; `register()` lại thành công.
4. **Hủy vì lỗi:** một worker đến và chờ trên `Phaser(2)`; coordinator `forceTermination()` khiến waiter nhận phase âm.
5. **Hook ném lỗi:** subclass cố tình ném `IllegalStateException`; xác nhận exception được truyền và phase không advance; cleanup bằng `forceTermination()`.

Chương trình **không sử dụng sleep** để đoán thread scheduling. Hai workers cho fixed rounds có đúng hai thread pool workers để mỗi party có thể đến barrier. Results chỉ in **sau `Future.get(timeout)`**, nên thứ tự output quyết định. Những chuyển phase do hook ghi lại theo chính thứ tự các phase. Pool do chương trình sở hữu được dừng có thời hạn.

Tạo file `src/main/java/demo/PhaserTerminationExample.java`:

~~~java
package demo;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.Phaser;
import java.util.concurrent.TimeUnit;

public final class PhaserTerminationExample {
    private PhaserTerminationExample() {}

    private static final class FixedRoundsPhaser extends Phaser {
        private final int rounds;
        private final List<String> transitions = new ArrayList<>();

        FixedRoundsPhaser(int parties, int rounds) {
            super(parties);
            if (rounds <= 0) {
                throw new IllegalArgumentException("rounds must be positive");
            }
            this.rounds = rounds;
        }

        @Override
        protected boolean onAdvance(int phase, int registeredParties) {
            transitions.add("phase=" + phase + ",parties=" + registeredParties);
            return registeredParties == 0 || phase >= rounds - 1;
        }

        List<String> transitions() {
            return List.copyOf(transitions);
        }
    }

    private static int doRounds(Phaser phaser, int rounds) {
        int completed = 0;
        for (int i = 0; i < rounds; i++) {
            int next = phaser.arriveAndAwaitAdvance();
            if (i < rounds - 1 && next < 0) {
                throw new IllegalStateException("Terminated too early");
            }
            if (i == rounds - 1 && !phaser.isTerminated()) {
                throw new IllegalStateException("Did not terminate");
            }
            completed++;
        }
        return completed;
    }

    public static void main(String[] args) throws Exception {
        Phaser defaultPhaser = new Phaser(1);
        int before = defaultPhaser.getPhase();
        int arrivedAt = defaultPhaser.arriveAndDeregister();
        System.out.println("default-arrival=" + arrivedAt);
        System.out.println("default-was-phase=" + before);
        System.out.println("default-terminated=" + defaultPhaser.isTerminated());
        System.out.println("default-phase-negative=" + (defaultPhaser.getPhase() < 0));

        FixedRoundsPhaser limited = new FixedRoundsPhaser(2, 3);
        Phaser reusable = new Phaser(1) {
            @Override
            protected boolean onAdvance(int phase, int registeredParties) {
                return false;
            }
        };
        Phaser forced = new Phaser(2);
        Phaser faulty = new Phaser(1) {
            @Override
            protected boolean onAdvance(int phase, int registeredParties) {
                throw new IllegalStateException("hook failure");
            }
        };
        ExecutorService workers = Executors.newFixedThreadPool(2);
        try {
            Future<Integer> first = workers.submit(() -> doRounds(limited, 3));
            Future<Integer> second = workers.submit(() -> doRounds(limited, 3));
            int a = first.get(5, TimeUnit.SECONDS);
            int b = second.get(5, TimeUnit.SECONDS);
            System.out.println("fixed-worker-rounds=" + a + "," + b);
            System.out.println("fixed-hook-transitions=" + limited.transitions());
            System.out.println("fixed-terminated=" + limited.isTerminated());
            System.out.println("fixed-phase-negative=" + (limited.getPhase() < 0));
            System.out.println("fixed-registered=" + limited.getRegisteredParties());

            reusable.arriveAndDeregister();
            System.out.println("override-zero-registered="
                    + reusable.getRegisteredParties());
            System.out.println("override-zero-terminated="
                    + reusable.isTerminated());
            System.out.println("override-next-phase=" + reusable.getPhase());
            int registrationPhase = reusable.register();
            System.out.println("override-register-phase=" + registrationPhase);
            reusable.arriveAndDeregister();
            reusable.forceTermination();
            System.out.println("override-forced-terminated="
                    + reusable.isTerminated());

            CountDownLatch arrivalRecorded = new CountDownLatch(1);
            Future<Integer> waiter = workers.submit(() -> {
                int arrivalPhase = forced.arrive();
                arrivalRecorded.countDown();
                return forced.awaitAdvanceInterruptibly(
                        arrivalPhase, 5, TimeUnit.SECONDS);
            });
            if (!arrivalRecorded.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Waiter did not arrive");
            }
            forced.forceTermination();
            System.out.println("forced-waiter-negative="
                    + (waiter.get(5, TimeUnit.SECONDS) < 0));

            boolean hookThrew = false;
            try {
                faulty.arriveAndAwaitAdvance();
            } catch (IllegalStateException expected) {
                hookThrew = "hook failure".equals(expected.getMessage());
            }
            System.out.println("faulty-hook-threw=" + hookThrew);
            System.out.println("faulty-phase-not-advanced="
                    + (faulty.getPhase() == 0));
        } finally {
            limited.forceTermination();
            reusable.forceTermination();
            forced.forceTermination();
            faulty.forceTermination();
            workers.shutdown();
            if (!workers.awaitTermination(5, TimeUnit.SECONDS)) {
                workers.shutdownNow();
                throw new IllegalStateException("Workers did not terminate");
            }
        }
        System.out.println("workers-terminated=" + workers.isTerminated());
    }
}
~~~

**Biên dịch và chạy với JDK 21** từ thư mục chứa `src/`:

~~~sh
javac --release 21 -encoding UTF-8 -Xlint:all -d out src/main/java/demo/PhaserTerminationExample.java
java -cp out demo.PhaserTerminationExample
~~~

**Stdout chính xác đã kiểm thử trên Java 21:**

~~~text
default-arrival=0
default-was-phase=0
default-terminated=true
default-phase-negative=true
fixed-worker-rounds=3,3
fixed-hook-transitions=[phase=0,parties=2, phase=1,parties=2, phase=2,parties=2]
fixed-terminated=true
fixed-phase-negative=true
fixed-registered=2
override-zero-registered=0
override-zero-terminated=false
override-next-phase=1
override-register-phase=1
override-forced-terminated=true
forced-waiter-negative=true
faulty-hook-threw=true
faulty-phase-not-advanced=true
workers-terminated=true
~~~

### 9.1. Đọc kết quả mặc định

`default-arrival=0` là **phase của lượt `arriveAndDeregister`**; nó **không cần âm** dù phaser đã terminated ngay sau đó. `default-terminated=true` và `default-phase-negative=true` mới xác nhận trạng thái cuối. Cụ thể ở `new Phaser(1)`, party cuối rút khiến hook mặc định kết thúc phaser.

### 9.2. Đọc kết quả fixed rounds

- `fixed-worker-rounds=3,3`: hai workers mỗi bên hoàn tất ba vòng; mã không giả định thứ tự thread nào tới trước.
- `fixed-hook-transitions=[phase=0,parties=2, phase=1,parties=2, phase=2,parties=2]`: hook chạy **một lần mỗi phase**, với phase **trước transition** và registered parties bằng 2.
- `fixed-terminated=true`: hook trả true ở phase 2 cho giới hạn ba vòng.
- `fixed-phase-negative=true`: `getPhase` âm sau termination.
- `fixed-registered=2`: hai parties **vẫn registered**; termination do giới hạn vòng **không tự deregister** chúng. Điều này khác trường hợp mặc định “registered về 0”.

Đây là điểm rất quan trọng: **termination không có nghĩa tất cả parties đã rút đăng ký**. `getRegisteredParties` là count đăng ký, còn `isTerminated` là lifecycle state. Sau termination, đừng dùng `getArrivedParties`/`getUnarrivedParties` để quản lý tiến độ, vì Javadoc không bảo đảm ý nghĩa các count ấy.

### 9.3. Đọc kết quả giữ sống với 0 party

`override-zero-registered=0` đồng thời `override-zero-terminated=false` chứng minh override `onAdvance` trả false cho phép phaser **còn sống dù không có party**. `override-next-phase=1`, `override-register-phase=1` chứng minh đăng ký lại ở phase 1 có tác dụng. Sau lần rút thứ hai, `forceTermination` chủ động dừng.

### 9.4. Đọc kết quả forceTermination

`forced-waiter-negative=true` cho thấy waiter đang chờ một phase từ `Phaser(2)` nhận **phase âm** sau `forceTermination()`, mặc dù party thứ hai không báo arrival. Force termination không chờ đến barrier đầy đủ; nó báo ngừng đồng bộ để chương trình xử lý lỗi.

### 9.5. Đọc kết quả hook ném exception

`faulty-hook-threw=true` chứng tỏ exception không được tự chuyển thành `onAdvance(true)`. `faulty-phase-not-advanced=true` chứng tỏ phase không advance sau hook lỗi. Do đó khi hook có nguy cơ throw, phải thiết kế error boundary/forceTermination thích hợp, không chờ các bên khác tự thoát.

### 9.6. Dọn tài nguyên

`workers-terminated=true` xác nhận executor do demo sở hữu đã `shutdown` và `awaitTermination` thành công. `finally` cũng forceTerm các phasers thử nghiệm trước khi dừng executor để giải phóng waiter trong đường lỗi. Nếu production có nhiều tasks, không nên giả định `forceTermination` đã ngắt tất cả I/O hoặc làm code nghiệp vụ tự ngừng; tasks cần quan sát cancellation/termination state.

## 10. Phân biệt rõ các giá trị trả về

| API | Điều thực hiện | Giá trị trả về |
| --- | --- | --- |
| `register()` | Đăng ký thêm party | Arrival phase được đăng ký; **âm nếu terminated** |
| `bulkRegister(n)` | Đăng ký thêm n parties | Phase áp dụng hoặc âm nếu terminated |
| `arrive()` | Báo arrival, không chờ | **Arrival phase** hoặc âm nếu terminated |
| `arriveAndDeregister()` | Báo arrival và rút party | **Arrival phase** hoặc âm nếu terminated |
| `arriveAndAwaitAdvance()` | Báo arrival và đợi phase tiếp | Kết quả theo contract arrival/advance; khi terminated trả phase âm theo semantics của API |
| `awaitAdvance(int phase)` | Chờ phase argument không còn hiện hành | Phase sau transition, hoặc argument âm, hoặc phase âm khi terminated |
| `awaitAdvanceInterruptibly(...)` | Chờ có interrupt/timeout | Phase/negative hoặc exception |
| `isTerminated()` | Quan sát trạng thái kết thúc | `boolean` |
| `getPhase()` | Quan sát phase hiện tại | Phase không âm, hoặc **âm khi terminated** |
| `forceTermination()` | Buộc dừng | `void` |

**Không dùng một dấu hiệu riêng lẻ để suy ra mọi kết quả:** callback/return của một arrival có thể không đủ làm dấu “shutdown đã hoàn tất” theo ý nghĩa nghiệp vụ. Hãy kiểm tra `isTerminated`, propagate lỗi và chờ executor/tasks với deadline riêng.

### 10.1. Vì sao phase âm là dấu termination?

Phase number bình thường bắt đầu từ 0 và tăng qua các transitions. Khi terminated, API dùng **một mã âm**. Không sử dụng mã âm đó như “phase -1” hay chỉ số vòng kinh doanh hợp lệ. Nếu cần biết phase gần nhất trước termination, Javadoc có cách mã hóa và phép trích xuất, nhưng trong code phổ biến chỉ cần `isTerminated()` và log phase cuối do ứng dụng ghi trước stop.

### 10.2. Phase number có wrap

`getPhase()` có thể wrap về 0 sau `Integer.MAX_VALUE` khi phaser chạy qua rất nhiều phase. Vì vậy nếu dùng `phase >= rounds - 1` để giới hạn vòng, chỉ nên dùng cho quy trình **ngắn, bắt đầu phase 0 và không wrap**. Với quy trình kéo dài không giới hạn, dùng điều kiện lifecycle/đếm vòng riêng có contract overflow phù hợp và synchronization đúng.

## 11. Vòng đời party và sự khác nhau giữa kết thúc với rút đăng ký

Có ba tình huống mà ứng dụng dễ nhầm:

~~~text
A. Một party cuối cùng gọi arriveAndDeregister:
   registered -> 0
   onAdvance mặc định -> true
   isTerminated -> true

B. Các parties vẫn registered nhưng onAdvance trả true ở phase cuối:
   registered vẫn > 0
   isTerminated -> true
   getPhase -> âm

C. Ứng dụng forceTermination do lỗi:
   registered không tự giảm
   waiters được giải phóng
   isTerminated -> true
~~~

Từ đó rút ra:

- **Đăng ký** là nghĩa vụ tham gia barrier.
- **Arrival** là báo hoàn tất một phase.
- **Deregistration** là rút khỏi những nghĩa vụ ở các phase sau.
- **Termination** là kết thúc vòng đời đồng bộ của phaser, không đồng nghĩa mọi task/party đã hoàn tất business work.
- **Force termination** là abort synchronization, không đảm bảo mọi worker đã cleanup.

Trong ứng dụng có nhiều workers, cần theo dõi job state/transaction/outbound data độc lập với trạng thái Phaser. `isTerminated()` không phải bằng chứng một file đã được ghi đủ hay một database transaction đã commit.

### 11.1. Khi lỗi xảy ra trước khi arrival

Nếu một registered party throw exception trước khi gọi `arrive`, những parties khác có thể **đợi mãi** nếu ứng dụng chỉ chờ barrier. Một recovery policy có thể bắt lỗi tại worker boundary, lưu nguyên nhân vào một `AtomicReference<Throwable>`, gọi `forceTermination()` và báo kết quả cho coordinator. Những workers được giải phóng phải thấy phaser đã terminated và thoát theo chính sách.

Không cố “sửa” bằng cách coordinator gọi `arrive()` thay party lỗi mà không có ownership rõ: Phaser không tự biết identity của party, nên arrival thay tùy tiện có thể khiến phase advance trước khi xử lý đúng.

### 11.2. Khi hết deadline

`awaitAdvanceInterruptibly(phase, timeout,unit)` có thể ném `TimeoutException`, nhưng **nó không tự deregister party, không tự force terminate**. Coordinator quyết định tiếp tục đợi, retry, hay abort cả nhóm. Nếu fail-fast, gọi forceTermination (có log lỗi/metrics) giúp các parties còn lại không bị treo.

Nếu timeout từ một task nhưng server muốn các parties khác tiếp tục, phải có mô hình thay party/deregister đúng phase, không tự giảm count khi party đã arrival trong phase ấy.

## 12. Những quy tắc để override `onAdvance` an toàn

| Quy tắc | Giải thích |
| --- | --- |
| Return `true` để kết thúc, `false` để tiếp tục | Đây là contract trực tiếp của hook |
| Phân biệt `phase` trước transition | Tránh off-by-one khi dừng sau N vòng |
| Hiểu `registeredParties` ở thời điểm hook | Không phải tổng tasks đã từng đăng ký |
| Hook chỉ chạy khi cuối phase advance | Không chạy ở mọi arrival |
| Giữ hook nhanh, không block | Không trì hoãn mọi waiters |
| Không gọi `register/arrive/await` trên cùng phaser trong hook | Kết quả không được đặc tả |
| Không sử dụng phase getters thay barrier | Getter snapshots không phải cơ chế sync |
| Không throw unchecked để “yêu cầu dừng” | Throw khiến phase không advance; dùng return true hoặc forceTermination |
| Nếu hook có thể throw, có recovery | Bắt lỗi ở boundary, forceTerminate để giải phóng waiters |
| Theo dõi lý do dừng riêng | Phaser chỉ chứa trạng thái đồng bộ, không phải business exception |
| Sau termination đừng register lại | Đã terminated thì register không có hiệu lực |
| Đừng nhầm forceTermination với cancel threads/I/O | Bắt buộc cleanup nghiệp vụ/executor riêng |
| Với tiered phasers, hook ở root | Không mong mọi child hook được gọi |
| Không giả định một thread cụ thể gọi hook | Party tới cuối có thể là bất kỳ worker |
| Tránh công bố mutable log chưa đồng bộ | Đọc sau completion hoặc dùng synchronization |
| Nếu cần dừng theo giờ, có coordinator | Hook chỉ chạy ở điểm advance; không tự tick theo đồng hồ |

### 12.1. Hạn chế khi triển khai tiered phasers

`Phaser` có thể được tổ chức thành cây để giảm contention khi có nhiều parties. Đối với một **nhóm tiered**, `onAdvance` chỉ được gọi ở **root phaser** mỗi khi cả cây advance. Do đó subclass child rồi trông đợi `onAdvance` của nó quyết định termination từng vùng là một giả định không đúng contract. Thiết kế termination condition ở root hoặc chia thành các phasers độc lập nếu cần policy dừng riêng biệt.

Nếu gọi `forceTermination()` trên một phaser thuộc cây, toàn bộ phasers liên quan cũng terminated. Đây là hành vi mạnh: phải bảo đảm việc abort một vùng không làm dừng nhầm workflow còn cần hoạt động.

### 12.2. Không giữ phép đếm quá lớn trong `onAdvance`

Hook có thể cập nhật một counter nhỏ, nhưng không nên scan hàng triệu records hoặc merge cấu trúc lớn trong nó. Nếu cần tính tổng kết quả các workers sau từng phase, workers nên publish kết quả theo thread-safe ownership trước arrival; hook chỉ kích hoạt một bước rất nhẹ, còn phép xử lý nặng chạy ở phase tiếp theo hoặc một executor nghiệp vụ phù hợp.

## 13. Các lỗi thường gặp và cách sửa

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Coi `onAdvance` chạy sau từng `arrive` | Đếm vòng sai | Nó chạy khi lượt arrival cuối gây advance |
| Tưởng tham số `phase` là phase mới | Dừng sớm/trễ một vòng | Nó là phase **đang hoàn tất** |
| Viết `phase >= rounds` thay vì `rounds-1` | Thường chạy dư một vòng | Tính 0-based phase |
| Không giữ điều kiện `registeredParties==0` trong custom hook dù muốn default semantics | Phaser sống khi không còn party | Trả true nếu parties==0 |
| Override luôn false rồi chờ phaser tự terminated | Có thể chờ vô hạn | Có `forceTermination`/điều kiện stop khác |
| Tưởng `new Phaser()` 0 party là terminated | Nhầm lifecycle | Nó bắt đầu chưa terminated |
| Tưởng `forceTermination` làm registered=0 | Metrics/state sai | Registered counts không tự giảm |
| Tưởng hook true tự đóng thread/executor | Rò rỉ tài nguyên | Cleanup executor và worker state riêng |
| Đọc arrived/unarrived sau termination để điều phối | Values không có bảo đảm | Dùng `isTerminated` và app state |
| Register lại trên terminated phaser | Không có hiệu lực | Tạo phaser mới khi cần |
| Hook gọi `arriveAndAwaitAdvance` trên chính mình | Có thể kẹt/kết quả không được đặc tả | Không gọi arrival/wait trong hook |
| Hook gọi `register()` trong lúc advance | Hành vi không được đặc tả | Điều phối registration ngoài hook |
| Hook ném lỗi để dừng | Phase không advance, waiters kẹt | Trả true hoặc forceTermination |
| Làm blocking I/O trong hook | Chậm/tắc toàn barrier | Hook nhanh, xử lý I/O ngoài |
| Dùng `Thread.sleep` để đợi phase | Race/flakiness | Dùng barrier, future, latch |
| Register nhiều parties hơn thread pool có thể đưa tới barrier | Starvation | Đảm bảo thực thi/khả năng tiến triển |
| Double-arrive cùng phase | Sai counts/lỗi dùng API | Một arrival mỗi party mỗi phase |
| Timeout trong `awaitAdvanceInterruptibly` rồi quên cleanup | Waiters khác có thể treo | Recovery/forceTerminate theo policy |
| Coi negative phase là business failure reason | Thiếu lý do lỗi | Lưu exception/reason riêng |
| Dùng phase như monotonic ID vĩnh viễn | Wrap sau `Integer.MAX_VALUE` | Dùng generation business ID riêng |
| Hook ghi `ArrayList` và thread khác đọc đồng thời | Race trên log | Read sau futures hoặc synchronize |
| Hủy child trong tiered phaser tưởng chỉ một vùng dừng | Dừng cả cây | Quản lý root/ownership rõ |

## 14. Bài tập tự kiểm tra có đáp án

**Câu 1.** `Phaser.onAdvance` được gọi sau mỗi registered party arrival đúng không?  
**Đáp án:** Không. Hook được gọi khi party cuối làm phase chuẩn bị advance, một lần mỗi phase chuyển bình thường.

**Câu 2.** `onAdvance(2, 5)` trả true thì phaser có chạy phase 3 bình thường không?  
**Đáp án:** Không. Nó chuyển sang trạng thái terminated tại ranh giới phase 2.

**Câu 3.** Muốn chạy bốn vòng bắt đầu phase 0 thì điều kiện trong hook là gì?  
**Đáp án:** `return phase >= 3 || registeredParties == 0;`, với `rounds=4`.

**Câu 4.** Vì sao kiểm tra `registeredParties==0` trong hook custom?  
**Đáp án:** Để duy trì điều kiện dừng mặc định khi mọi party rút, không để phaser sống vô ích, nếu đó là policy mong muốn.

**Câu 5.** `new Phaser(0)` có terminated ngay không?  
**Đáp án:** Không. Nó khởi tạo phase 0, không có parties, vẫn có thể register.

**Câu 6.** `new Phaser(1)`, gọi `arriveAndDeregister`, trạng thái?  
**Đáp án:** Registered về 0, hook mặc định trả true, `isTerminated()==true`, `getPhase()<0`; return arrival phase ban đầu bằng 0.

**Câu 7.** Override `onAdvance` luôn trả false và deregister party cuối, phaser có tiếp tục cho register mới không?  
**Đáp án:** Có. Nó có thể advance dù registered=0, không terminated, rồi nhận registration mới.

**Câu 8.** Một phaser đã terminated rồi gọi `register` sẽ hồi sinh?  
**Đáp án:** Không. Registration không có hiệu lực, nhận phase âm. Muốn workflow mới, tạo phaser mới hoặc thiết kế trước để không terminate tại 0.

**Câu 9.** `forceTermination` có chờ mọi party đến trước khi kết thúc không?  
**Đáp án:** Không. Nó kết thúc ngay và giải phóng waiters.

**Câu 10.** `forceTermination` có làm mọi thread dừng và tự rollback database không?  
**Đáp án:** Không. Thread/task/transaction cleanup là trách nhiệm ứng dụng.

**Câu 11.** Khi hook ném `RuntimeException`, phase đã advance chưa?  
**Đáp án:** Chưa theo Javadoc; exception truyền lên party kích hoạt advance. Phải có recovery (thường forceTerminate).

**Câu 12.** Trong hook có thể gọi `awaitAdvance(phase)` trên cùng phaser để đợi vòng mới?  
**Đáp án:** Không nên; tác động không được đặc tả và có nguy cơ tự đợi sự kiện hook đang ngăn.

**Câu 13.** Có nên làm HTTP request chậm trong hook không?  
**Đáp án:** Không. Hook chạy trong thread last-arrival, có thể trì hoãn mọi party.

**Câu 14.** Với tiered phasers, `onAdvance` của child nào cũng chạy mỗi phase?  
**Đáp án:** Không. Hook ở root phaser theo contract.

**Câu 15.** Vì sao example dùng hai workers với `FixedRoundsPhaser(2,3)`?  
**Đáp án:** Để cả hai registered parties có thread chạy tới barrier và demo không bị executor starvation.

**Câu 16.** Tại sao sau custom termination số registered có thể vẫn bằng 2?  
**Đáp án:** Hook trả true kết thúc phaser, không tự deregister các parties; registration count và termination là khái niệm khác nhau.

**Câu 17.** Vì sao cần xét `isTerminated()` ở vòng cuối thay vì tin mọi giá trị return của `arriveAndAwaitAdvance()` luôn âm?  
**Đáp án:** Giá trị trả về theo semantics arrival/advance có sắc thái ở lượt gây kết thúc; `isTerminated` là kiểm tra trạng thái kết thúc rõ ràng.

**Câu 18.** Timeout của `awaitAdvanceInterruptibly` có làm phaser tự terminated không?  
**Đáp án:** Không. Chỉ ứng dụng gọi `forceTermination`/có custom policy thì phaser mới kết thúc.

**Câu 19.** `getPhase() < 0` cho biết gì?  
**Đáp án:** Phaser đã terminated. Sử dụng `isTerminated()` để diễn đạt rõ mục đích.

**Câu 20.** Hook có thể ghi danh sách transitions dùng chung mà caller đọc live không synchronization?  
**Đáp án:** Không nên. Dùng synchronization/concurrent data structure hoặc đọc sau khi Future/join bảo đảm các hook đã hoàn tất.

**Câu 21.** `forceTermination` một child tiered phaser chỉ ngừng child đó?  
**Đáp án:** Không; theo contract cả nhóm tiered phasers có thể terminated.

**Câu 22.** Khi hook hoàn tất ba vòng, có nghĩa mọi requests đã lưu bền vững ở DB chưa?  
**Đáp án:** Không. Phaser đảm bảo arrivals/happens-before giữa các phase, không phải kết quả transaction hay application ACK.

## 15. Checklist review code

- [ ] Xác định dừng mặc định, giới hạn vòng hay hủy vì lỗi là chính sách nào.
- [ ] Hook override đúng `protected boolean onAdvance(int phase,int registeredParties)`.
- [ ] Hiểu phase argument là **phase trước advance**, không bị off-by-one.
- [ ] Kiểm tra `rounds > 0` và đơn vị vòng là gì.
- [ ] Nếu muốn mặc định dừng khi không còn party, giữ `registeredParties == 0`.
- [ ] Nếu muốn cho phép đăng ký lại khi count 0, override false có chủ đích và có đường shutdown.
- [ ] Không coi `getRegisteredParties()==0` tương đương `isTerminated()`.
- [ ] Không coi termination làm registered về 0.
- [ ] Không gọi `register`/`arrive`/`await` trên cùng Phaser trong hook.
- [ ] Hook không block, không thực hiện I/O lâu hoặc chờ task sau phase.
- [ ] Có recovery khi hook throw unchecked; thường `forceTermination` giải phóng waiters.
- [ ] Không dùng unchecked throw như cách dừng bình thường; return true.
- [ ] Kiểm tra `isTerminated()`/negative phase sau lời chờ, không chạy thêm business round.
- [ ] `forceTermination` được dùng đúng scope, đặc biệt khi có tiered phasers.
- [ ] Sau forceTermination, propagate cancellation và cleanup jobs/executor riêng.
- [ ] Chọn `awaitAdvanceInterruptibly` nếu cần interruption/timeout; xử lý timeout chủ động.
- [ ] Không double arrival/deregister trong một phase.
- [ ] Đăng ký parties trước khi submit tasks và đảm bảo đủ thread capacity để đến barrier.
- [ ] Không dựa vào getters như cơ chế synchronization, vì snapshots có thể là transient.
- [ ] Không đọc arrived/unarrived sau termination để đưa ra quyết định.
- [ ] Test N=1, N=2, N=3, registered 0, forceTermination, hook throw và reregistration.
- [ ] Với tiered phasers, thiết kế termination tại root.
- [ ] Không dùng phase number làm unique ID vĩnh viễn vì có wrap.
- [ ] Không cho nhiều threads đọc cùng một mutable hook log khi thiếu coordination.
- [ ] Dọn tài nguyên/phát kết quả lỗi theo business protocol, không coi termination là rollback.
- [ ] Không sử dụng kiến thức legacy; đối chiếu tài liệu Java SE hiện hành.

## 16. Nguồn chính thức Java SE 21

- [Phaser](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Phaser.html): `onAdvance` default/custom, hook invocation constraints, termination, `forceTermination`, tiered phasers, returns, parties và phase.
- [CountDownLatch](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CountDownLatch.html): điều phối điểm quan sát ổn định của waiter trong demo.
- [ExecutorService](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html): executor lifecycle và trách nhiệm cleanup.
- [Future](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Future.html): chờ task result có timeout và lỗi.
- [TimeUnit](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/TimeUnit.html): thời hạn chờ trong chương trình mẫu.
- [Java Language Specification — Memory Model](https://docs.oracle.com/javase/specs/jls/se21/html/jls-17.html): visibility/happens-before, bổ sung cho contract đồng bộ của Phaser.

**Kết luận:** `Phaser` có hai con đường kết thúc khác nhau: hook `onAdvance` quyết định **kết thúc tại ranh giới phase** bằng `true`, còn `forceTermination()` **buộc kết thúc ngay** để giải phóng waiters khi lỗi/hủy. Mặc định, deregistration làm registered về 0 kích hoạt termination; override có thể giới hạn số vòng hoặc cho phép đăng ký lại. Để đúng trên JDK hiện đại, cần hiểu tham số phase trước chuyển, tránh off-by-one, giữ hook nhanh/không tái nhập API Phaser, kiểm tra `isTerminated()`, và dọn các threads/transactions riêng.
