# Phase, số bên tham gia và số bên chưa đến trong `Phaser` của Java

## 1. Câu hỏi trung tâm: một đợt đồng bộ đang ở đâu?

Khi nhiều tác vụ xử lý song song một quy trình gồm nhiều bước, đôi khi tất cả phải **hoàn thành bước hiện tại** rồi mới được bắt đầu bước kế tiếp. Java cung cấp `java.util.concurrent.Phaser` — một **rào chắn đồng bộ tái sử dụng được** (*reusable synchronization barrier*) hỗ trợ số lượng bên tham gia thay đổi trong thời gian chạy.

`Phaser` lưu những thông tin quan trọng:

- **Phase (giai đoạn)**: thế hệ/vòng đồng bộ hiện tại, tra cứu bằng `getPhase()`.
- **Registered parties (số bên đã đăng ký)**: số đơn vị đồng bộ đang tham gia, tra cứu bằng `getRegisteredParties()`.
- **Arrived parties (số bên đã đến)**: số bên đã báo hoàn thành phần việc của **phase hiện tại**, tra cứu bằng `getArrivedParties()`.
- **Unarrived parties (số bên chưa đến)**: số bên còn phải báo đến để phase hiện tại có thể tiến, tra cứu bằng `getUnarrivedParties()`.

Bài này giải thích **chính xác ý nghĩa và mối quan hệ của bốn giá trị** ấy; cách `register()`, `bulkRegister(int)`, `arrive()`, `arriveAndAwaitAdvance()` và `arriveAndDeregister()` làm thay đổi chúng; giới hạn của việc đọc số liệu khi nhiều thread cùng chạy; và cách nhận biết trạng thái kết thúc.

**Đề bài trực tiếp:** “Phase, số bên tham gia và số bên chưa đến” trong nhóm **Phaser**.

**Lưu ý phiên bản:** `Phaser` là API có từ Java 7 (Java SE 7) và **vẫn được hỗ trợ trên Java 17, 21 và các JDK hiện đại**. Mã chương trình đầy đủ dùng API hiện hành và được kiểm thử trên **Java 21**. Nội dung tuân thủ ghi chú module: **chỉ sử dụng kiến thức còn áp dụng, không khuyến nghị kiến thức lỗi thời hoặc legacy**.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Vẽ trạng thái một `Phaser` bằng bộ bốn `(phase, registered, arrived, unarrived)`.
2. Giải thích vì sao trong **một snapshot ổn định**, `registered = arrived + unarrived`.
3. Phân biệt **đăng ký party**, **báo đến**, **đến rồi đợi**, **đến rồi rút đăng ký**.
4. Hiểu thời điểm cuối cùng làm `phase` tiến và các bộ đếm `arrived/unarrived` bắt đầu chu kỳ mới.
5. Biết `getRegisteredParties()/getUnarrivedParties()` chỉ là dữ liệu **monitoring**, không phải cách an toàn để quyết định tiến hành bước nghiệp vụ.
6. Nhận biết `getPhase()` âm khi terminated và vì sao những bộ đếm sau termination không mang ý nghĩa để ra quyết định.
7. Viết một ví dụ Java 21 có nhiều thread, quan sát chính xác counts tại các thời điểm được phối hợp.
8. Tránh lỗi thiếu deregister, arrive hai lần, đăng ký muộn, dùng timeout không cleanup, hoặc nhầm party với thread.

## 2. Phaser là gì và một party là gì?

`Phaser` tương tự một barrier cho nhiều lần lặp, nhưng số lượng **parties** tham gia có thể thay đổi. Một **party** là một **đơn vị đăng ký trong quy tắc đồng bộ**, thường ứng với một worker, task hoặc một thread có trách nhiệm báo đến một lần mỗi phase. **Phaser không duy trì danh sách ID của thread hoặc task.** Các hàm đăng ký/đến chỉ điều chỉnh số đếm nội bộ, nên ứng dụng phải tự bảo đảm mỗi party được đăng ký, đến và rút đúng số lần.

Điều này giải thích hai kết luận quan trọng:

- `getRegisteredParties()==3` có nghĩa **ba parties** đang được tính vào barrier, **không** có nghĩa hiện đang có đúng ba OS threads chạy.
- Một thread có thể điều phối nhiều parties nếu ứng dụng tổ chức như vậy; nhưng nếu cùng một party gọi `arrive()` hai lần trong một phase thì đó là **lỗi sử dụng**, kể cả thread vẫn là thread cũ.

### 2.1. Khởi tạo một Phaser

~~~java
Phaser empty = new Phaser();
Phaser group = new Phaser(3);
~~~

Đây là đoạn **minh họa độc lập về constructor** (cần `import java.util.concurrent.Phaser;`).

- `new Phaser()` tương đương tạo phaser ban đầu có **0 parties**, phase ban đầu **0**. Điều đó **không có nghĩa nó đã terminated** ngay từ constructor. Có thể gọi `register()` về sau.
- `new Phaser(3)` tạo một phaser có ba registered parties; ban đầu ở phase 0, chưa ai đến nên `registered=3, arrived=0, unarrived=3`.
- Số parties khởi tạo không được âm hay vượt giới hạn hỗ trợ; nếu không hợp lệ, constructor ném `IllegalArgumentException`. Triển khai Java SE 21 giới hạn tối đa **65.535 parties trên một Phaser** và có thể dùng tiered phasers cho nhóm rất lớn.

### 2.2. Trạng thái ban đầu theo ví dụ

~~~text
Phaser p = new Phaser(3)

getPhase()             = 0
getRegisteredParties() = 3
getArrivedParties()    = 0
getUnarrivedParties()  = 3

Đã đến:       [ ]
Chưa đến:     [ A, B, C ]
Phase hiện tại: 0
~~~

Các phép đếm này phản ánh một điểm quan sát **chưa có thao tác đồng thời nào thay đổi p**. Nếu nhiều threads đồng thời arrive/register/deregister, bốn phép gọi getter không được gom thành một giao dịch đọc nguyên tử duy nhất.

## 3. Phase — số hiệu vòng đồng bộ

Mỗi thế hệ của `Phaser` có một số hiệu `phase`:

~~~text
phase 0: A đến, B đến, C đến -> chuyển sang phase 1
phase 1: A đến, B đến, C đến -> chuyển sang phase 2
phase 2: A đến, B đến, C đến -> chuyển sang phase 3
...
~~~

Khi tất cả các parties **đã đăng ký cho phase hiện tại** đều báo đến, rào chắn chuyển sang phase kế tiếp (trừ khi chính quá trình advance quyết định termination). Mỗi phase mới bắt đầu với những parties **còn đăng ký**:

~~~text
TRƯỚC advance                 SAU advance bình thường
phase = p                     phase = p + 1
registered = R                 registered = R' (theo đăng ký/rút thực tế)
arrived = R                   arrived = 0
unarrived = 0                 unarrived = R'
~~~

Trong ví dụ không có đăng ký/rút thêm ngay tại thời điểm transition, `R'=R`. Nếu có thao tác đồng thời, các snapshot có thể nhanh chóng thay đổi, do đó không nên đọc bảng này như một quy định về thứ tự quan sát từng getter.

### 3.1. `getPhase()` trả gì?

~~~java
int phase = phaser.getPhase();
~~~

- Trong trạng thái bình thường, giá trị không âm: bắt đầu từ **0**, tăng sau mỗi lần advance.
- Theo Javadoc, phase số học quay lại **0** sau khi vượt `Integer.MAX_VALUE`; vì vậy không dùng phase làm một ID duy nhất không giới hạn trong toàn vòng đời lâu dài.
- Khi terminated, `getPhase()` trả **giá trị âm**. Cách rõ ràng để kiểm tra là `phaser.isTerminated()`; không dựa vào một con số âm cụ thể.
- `getPhase()` cho biết phase **hiện tại**, không phải “số lượng công việc đã xử lý” hay thời điểm bắt đầu một task.

### 3.2. Phase tiến khi nào?

Một trong các parties gọi phương thức arrival đủ để **giảm unarrived xuống hết**. Lượt arrival cuối này kích hoạt optional hook `onAdvance(int phase, int registeredParties)`. Nếu hook trả `false` thì phaser tiếp tục phase mới; nếu trả `true` thì nó chuyển vào trạng thái terminated. Triển khai mặc định của `onAdvance` trả `true` khi **số registered parties đã về 0 do deregistration**.

Ví dụ một phaser chỉ còn một party:

~~~java
Phaser p = new Phaser(1);
int oldPhase = p.arriveAndAwaitAdvance();
int newPhase = p.getPhase();
// oldPhase được đặt tên ở đây theo kết quả trả về:
// arriveAndAwaitAdvance() trả phase sau advance, không phải phase trước.
~~~

Đây là đoạn minh họa ngắn. Sau một `arriveAndAwaitAdvance()` duy nhất, phase từ 0 sang 1, hàm trả về **1**. Khác với `arrive()`: hàm `arrive()` trả về **phase mà lần đến được ghi nhận**, không phải phase mới sau khi advance. Nhầm hai giá trị rất dễ làm ứng dụng chờ nhầm giai đoạn.

## 4. Ba bộ đếm quan trọng: registered, arrived, unarrived

### 4.1. `getRegisteredParties()` — tổng số parties còn đăng ký

~~~java
int registered = phaser.getRegisteredParties();
~~~

Đó là số lượng **bên đã đăng ký với phaser này**, gồm cả những bên **đã đến** và **chưa đến** trong phase hiện tại.

Tổng registered thay đổi khi:

- `register()` thêm **một party**.
- `bulkRegister(n)` thêm **n parties**.
- `arriveAndDeregister()` làm party vừa đến **rút khỏi phaser**, giảm registered một đơn vị.
- Một số tình huống có parent/tiered phasers ảnh hưởng đăng ký ở tầng cha; bộ đếm một phaser không phải tổng cộng parties của cả cây.

**`arrive()` và `arriveAndAwaitAdvance()` không tự rút đăng ký**, nên party thường vẫn cần báo đến ở phase tiếp theo.

### 4.2. `getArrivedParties()` — số parties đã báo đến trong phase

~~~java
int arrived = phaser.getArrivedParties();
~~~

Phản ánh số parties đăng ký **đã hoàn thành lượt arrival trong phase hiện tại**.

Giả sử phase 0 có 3 parties A, B, C, chưa ai đến: arrived=0. Khi A gọi `arrive()`, arrived tăng lên 1; khi B đến, arrived tăng tiếp lên 2; khi C đến, phase có thể advance, và arrived của **phase mới** trở về 0. Vì vậy, thấy `arrived=0` **không đủ chứng minh chưa có ai làm việc**: có thể phase vừa chuyển.

Nếu một party dùng `arriveAndDeregister()`, bản thân party đó **rời khỏi tổng registered**. Bạn không thể suy luận rằng arrived luôn tăng 1 theo cùng cách như một party vẫn còn đăng ký. Trạng thái sau thao tác deregister cần xét **cùng lúc** sự giảm của registered/unarrived.

### 4.3. `getUnarrivedParties()` — số parties còn phải báo đến

~~~java
int remaining = phaser.getUnarrivedParties();
~~~

Phản ánh số parties **chưa arrival trong phase hiện tại**. Đây không phải số parties “đang chạy” hay “đang bận CPU”. Một thread có thể bị treo, đã chạy xong nhưng chưa gọi arrival, hoặc mới register giữa phase, đều góp vào unarrived.

Trong một trạng thái ổn định chưa termination:

\[
\text{registered}=\text{arrived}+\text{unarrived}.
\]

Ví dụ:

| Thời điểm quan sát ổn định | Phase | Registered | Arrived | Unarrived |
| --- | ---: | ---: | ---: | ---: |
| Khởi tạo `new Phaser(3)` | 0 | 3 | 0 | 3 |
| A gọi `arrive()` | 0 | 3 | 1 | 2 |
| B gọi `arrive()` | 0 | 3 | 2 | 1 |
| C gọi `arrive()` kích hoạt advance | 1 | 3 | 0 | 3 |

Bảng giả định **không có đăng ký/rút thêm** trong khoảng thời gian minh họa. Một lần đến cuối cùng sẽ khiến phase tăng nên sau đó `unarrived` thường trở về số parties còn đăng ký, chứ không ở 0 đủ lâu để mã ứng dụng “đợi thấy 0” bằng polling.

### 4.4. Không dùng getters làm cơ chế điều phối

Javadoc Java SE 21 nêu rõ các phương thức truy vấn này thích hợp **monitoring**, vì chúng có thể phản ánh trạng thái chuyển tiếp nên **không phù hợp làm logic điều khiển đồng bộ**.

**Phản ví dụ:**

~~~java
while (phaser.getUnarrivedParties() > 0) {
    // Busy-wait cho tới khi mọi người đến?
}
// Tiếp tục bước tiếp theo: KHÔNG AN TOÀN.
~~~

Đây là **code không nên dùng**. Vì khi party cuối đến, phase có thể chuyển ngay và unarrived reset về R. Vòng lặp có thể spin vô hạn hoặc kết luận sai. Nó còn tốn CPU và không có hợp đồng chờ/cancellation đúng.

**Cách đúng:** party đã đăng ký gọi `arriveAndAwaitAdvance()` khi hoàn tất bước; nếu đã dùng `arrive()`, chờ bằng `awaitAdvance(arrivalPhase)`; khi muốn có interrupt/timeout, dùng `awaitAdvanceInterruptibly(...)`.

Ngoài ra, các getter gọi lần lượt **không là một snapshot nguyên tử xuyên suốt**. Bạn có thể đọc phase tại thời điểm t1, registered tại t2 và unarrived tại t3, đúng ngay khi đọc nhưng không cùng một trạng thái nhất quán. Khi log/metrics, ghi rõ đây là **quan sát xấp xỉ**, không dùng để khẳng định hệ thống đang có chính xác bao nhiêu thread hoạt động.

## 5. `register()` và `bulkRegister()` làm thay đổi số đếm

### 5.1. `register()` thêm một party chưa đến

~~~java
Phaser phaser = new Phaser(1);
int p = phaser.register();
~~~

Ban đầu `(phase=0, registered=1, arrived=0, unarrived=1)`. Sau `register()` (nếu không có thread khác arrival): `(phase=0, registered=2, arrived=0, unarrived=2)`. Hàm trả về phase mà registration có hiệu lực, ở đây `0`.

### 5.2. `bulkRegister(n)` thêm n parties

~~~java
Phaser phaser = new Phaser(1);
int registeredAtPhase = phaser.bulkRegister(2);
~~~

Ở trạng thái quiescent, số đếm thay đổi từ:

~~~text
Trước: phase=0, registered=1, arrived=0, unarrived=1
Sau:   phase=0, registered=3, arrived=0, unarrived=3
Return của bulkRegister(2): 0
~~~

- `bulkRegister(0)` không thêm party và có thể được dùng như một phép quan sát phase liên quan; nhưng nếu chỉ cần đọc phase hãy dùng `getPhase()`.
- `bulkRegister(n)` với `n<0` ném `IllegalArgumentException`.
- Đăng ký vượt ngưỡng hỗ trợ ném `IllegalStateException`.
- Khi đã terminated, registration không có hiệu lực và trả **phase âm**.
- Nếu `onAdvance` đang được thực thi, registration có thể phải chờ transition kết thúc trước khi trả về.

### 5.3. Đăng ký động trong phase có thể làm barrier chờ lâu hơn

Giả sử phase 4, registered=2, unarrived=1. Nếu một task mới gọi `register()` **trước khi phase advance**, số registered và unarrived cùng tăng; từ đó những parties cũ cần đợi cả task mới arrival để chuyển phase. Đây là hành vi đúng nhưng có thể gây lỗi thiết kế nếu thêm parties không có kế hoạch, ví dụ task mới chưa được submit hoặc executor không còn capacity.

**Quy tắc thực tế:** đăng ký **trước khi** công việc có khả năng đến barrier; quản lý rõ từng registration và nhánh dọn khi task không thể chạy. Một party được đăng ký nhưng không bao giờ arrival/deregister sẽ khiến các bên đang chờ có thể kẹt vô hạn.

## 6. Các phương thức báo đến và tác động lên counts

### 6.1. `arrive()`: đến nhưng không chờ

~~~java
int arrivalPhase = phaser.arrive();
~~~

`arrive()` báo rằng một registered party đã đến phase hiện tại và **trả phase của lượt arrival đó**. Nó **không chặn chờ** các bên khác. Party vẫn đăng ký cho các phase sau, trừ khi rút riêng.

Nếu party cuối cùng gọi arrive, phase có thể advance ngay. Do đó sau một lệnh `arrive()`, `getPhase()` có thể lớn hơn `arrivalPhase`.

Muốn đợi các parties khác sau khi đã arrive:

~~~java
int arrivalPhase = phaser.arrive();
int nextPhase = phaser.awaitAdvance(arrivalPhase);
~~~

Đây là đoạn minh họa của một **registered party**, với điều kiện không có một lời gọi arrive thứ hai cho cùng party ở phase ấy. `awaitAdvance` nhận **phase gốc do arrive trả về**. Chỉ `awaitAdvance` tự nó **không tính thêm một lần arrival**.

### 6.2. `arriveAndAwaitAdvance()`: đến rồi chờ

~~~java
int nextPhase = phaser.arriveAndAwaitAdvance();
~~~

Một registered party vừa arrival vừa **đợi tới khi tất cả các bên cần thiết cùng đến** và phase advance. Hàm trả về **phase sau khi advance** (hoặc phase âm nếu termination). Với phaser chưa terminated, đây là lựa chọn dễ đọc nhất cho barrier nhiều vòng.

Không gọi thêm `arrive()` rồi lại `arriveAndAwaitAdvance()` **trong cùng phase của cùng một party**. Như vậy tính double arrival; có thể ném `IllegalStateException` hoặc làm sai counts ở một thời điểm không dễ thấy.

### 6.3. `arriveAndDeregister()`: đến rồi rút khỏi phaser

~~~java
int arrivalPhase = phaser.arriveAndDeregister();
~~~

Khác với `arrive()`, method này **vừa báo đến vừa giảm số parties đã đăng ký** để các phase sau không còn phải chờ party ấy. Nó không đợi các bên khác hoàn tất. Giá trị trả về là **phase của lượt arrival**, hoặc âm nếu phaser terminated.

Ví dụ một trạng thái quiescent:

~~~text
Trước:  phase=0, registered=3, arrived=1, unarrived=2
B gọi arriveAndDeregister():
Sau:    phase=0, registered=2, arrived=1, unarrived=1
~~~

B được rút khỏi registered; số arrived của những parties còn đăng ký giữ nguyên 1. Nếu party rút chính là **lượt arrival cuối**, operation có thể gây advance hoặc termination khi số registered về 0.

### 6.4. Không có một phương thức “deregister không arrival” thông thường

`Phaser` cung cấp `arriveAndDeregister()`; vì vậy logic quản lý party phải biết party đã arrive trong phase hiện tại hay chưa. Không gọi nó bừa bãi sau một `arrive()` đã thực hiện **cho cùng phase** chỉ vì muốn giảm count: đó có thể là double arrival và sai hợp đồng.

Một party muốn rút khỏi các vòng về sau nên **deregister tại lượt arrival của phase mà nó còn phải hoàn tất**. Với cancellation/error sau khi phase đã arrival, ứng dụng cần xây một protocol điều phối an toàn và không tự sửa số đếm bằng extra arrival.

### 6.5. Bảng so sánh kết quả trả về

| Phương thức | Có cộng một lượt arrival? | Có chờ phase mới? | Có rút registration? | Return |
| --- | --- | --- | --- | --- |
| `register()` | Không | Không như barrier, có thể chờ `onAdvance` | Không | Phase hiệu lực đăng ký |
| `bulkRegister(n)` | Không | Không như barrier | Không | Phase hiệu lực đăng ký |
| `arrive()` | Có | Không | Không | **Arrival phase** |
| `arriveAndAwaitAdvance()` | Có | Có | Không | **Phase sau advance** hoặc âm |
| `arriveAndDeregister()` | Có | Không | Có | **Arrival phase** |
| `awaitAdvance(phase)` | **Không** | Có, nếu vẫn ở phase đã cho | Không | Phase hiện tại sau chờ |
| `awaitAdvanceInterruptibly(phase,timeout,unit)` | **Không** | Có, có interruption/timeout | Không | Phase sau chờ hoặc exception |

Quan sát phase/bộ đếm bằng getter **không làm party đến hay rút đăng ký**.

## 7. Minh họa từng trạng thái với ba parties

Giả sử A, B, C đã đăng ký, ở phase 0. A đến, B rút đăng ký, C đến cuối:

~~~text
                          phase   registered   arrived   unarrived
new Phaser(3)                0         3          0          3
A: arrive()                  0         3          1          2
B: arriveAndDeregister()     0         2          1          1
C: arrive()                  1         2          0          2
~~~

Giải thích:

1. A vẫn đăng ký, sẽ tiếp tục được tính cho phase 1.
2. B rút registration nên future phases không còn chờ B.
3. C đến làm unarrived của phase 0 hết, nên phaser chuyển sang phase 1.
4. Ở phase 1, **chỉ còn A và C**: registered=2, arrived=0, unarrived=2.

Đây là ví dụ mô phỏng trạng thái trong **thứ tự thao tác được kiểm soát**, không phải hướng dẫn dùng một thread gọi thay nhiều parties trong ứng dụng production. Phaser không tự theo dõi “A/B/C” nên chính ứng dụng phải bảo đảm identity/ownership.

### 7.1. Điểm dễ nhầm: khi phase mới bắt đầu, unarrived có thể tăng lại

Số `unarrived` giảm dần khi các parties đến trong **cùng phase**, nhưng sau advance nó **reset** để đếm những người còn phải đến ở phase tiếp theo. Vì vậy:

- `unarrived=2` ở phase 0 sau một người đến có nghĩa “còn hai arrivals”.
- `unarrived=2` ở phase 1 sau B rút có nghĩa “hai parties còn đăng ký đều chưa đến vòng mới”.
- Cùng một số 2 **không có cùng ý nghĩa thời gian** nếu phase khác nhau.

Một dashboard nên hiển thị **phase, registered, arrived, unarrived cùng nhau** và chú thích chúng là snapshot, chứ không chỉ hiển thị “remaining=2” bỏ mất phase.

## 8. Chương trình Java 21 đầy đủ: quan sát counts đúng thời điểm

Mục tiêu: chạy **hai worker thật** và một **main coordinator** cùng một `Phaser`, nhưng vẫn có output **quyết định**, không phụ thuộc việc OS chọn chạy worker nào trước.

Quy trình:

1. `Phaser(1)` đăng ký main là party đầu tiên: phase=0, registered=1, arrived=0, unarrived=1.
2. `bulkRegister(2)` đăng ký **hai worker** trước khi submit vào executor: registered=3, unarrived=3.
3. Mỗi worker gọi `arrive()`, rồi giảm một `CountDownLatch` để main biết arrival đã thực sự xảy ra; worker gọi `awaitAdvance(arrivalPhase)` và chờ.
4. Main chờ latch bằng `await(5,SECONDS)`: vì **main chưa arrival** nên phase 0 chưa thể advance. Lúc đó có một **quãng ổn định có thể kiểm chứng**: phase=0, registered=3, arrived=2, unarrived=1.
5. Main gọi `arriveAndAwaitAdvance()` làm party cuối của phase 0 đến; phase thành 1.
6. Các worker được giải phóng, rồi mỗi worker gọi `arriveAndDeregister()` **trong phase 1** trước khi trả kết quả; main nhận hai `Future<Integer>`.
7. Chỉ còn main đăng ký: phase=1, registered=1, arrived=0, unarrived=1.
8. Main gọi `arriveAndDeregister()`, registered về 0 và `Phaser` mặc định **terminated**.
9. In `isTerminated()` và chỉ kiểm tra `getPhase()<0`; không đọc hoặc suy luận ý nghĩa counters sau termination.
10. `finally` gọi `forceTermination()` để giải phóng waiters trong nhánh lỗi, sau đó dừng executor có thời hạn.

Các phép đọc counts được đặt **trước khi workers bắt đầu**, **trong lúc main đang giữ phase 0**, hoặc **sau khi cả worker Futures đã hoàn tất**. Điều này tránh phải dựa vào một snapshot của getter đang bị threads khác cập nhật.

Tạo tệp `src/main/java/demo/PhaserCountsExample.java`:

~~~java
package demo;

import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.Phaser;
import java.util.concurrent.TimeUnit;

public final class PhaserCountsExample {
    private PhaserCountsExample() {}

    private static String snapshot(Phaser phaser) {
        return "phase=" + phaser.getPhase()
                + ",registered=" + phaser.getRegisteredParties()
                + ",arrived=" + phaser.getArrivedParties()
                + ",unarrived=" + phaser.getUnarrivedParties();
    }

    private static Callable<Integer> worker(Phaser phaser,
                                              CountDownLatch bothArrived) {
        return () -> {
            int arrivalPhase = phaser.arrive();
            bothArrived.countDown();
            int nextPhase = phaser.awaitAdvance(arrivalPhase);
            phaser.arriveAndDeregister();
            return nextPhase;
        };
    }

    public static void main(String[] args) throws Exception {
        Phaser phaser = new Phaser(1); // Main is a registered party.
        System.out.println("initial=" + snapshot(phaser));

        int registrationPhase = phaser.bulkRegister(2);
        System.out.println("registration-phase=" + registrationPhase);
        System.out.println("after-register=" + snapshot(phaser));

        CountDownLatch bothArrived = new CountDownLatch(2);
        ExecutorService executor = Executors.newFixedThreadPool(2);
        try {
            Future<Integer> first = executor.submit(worker(phaser, bothArrived));
            Future<Integer> second = executor.submit(worker(phaser, bothArrived));

            if (!bothArrived.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Workers did not arrive");
            }
            System.out.println("workers-arrived=" + snapshot(phaser));

            int nextPhase = phaser.arriveAndAwaitAdvance();
            System.out.println("main-next-phase=" + nextPhase);

            int firstPhase = first.get(5, TimeUnit.SECONDS);
            int secondPhase = second.get(5, TimeUnit.SECONDS);
            System.out.println("workers-next-phase=" + firstPhase + "," + secondPhase);
            System.out.println("after-workers=" + snapshot(phaser));

            int deregistrationPhase = phaser.arriveAndDeregister();
            System.out.println("main-deregister-phase=" + deregistrationPhase);
            System.out.println("terminated=" + phaser.isTerminated());
            System.out.println("phase-negative=" + (phaser.getPhase() < 0));
        } finally {
            phaser.forceTermination(); // Release waiters if an earlier step fails.
            executor.shutdown();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
                throw new IllegalStateException("Executor did not terminate");
            }
        }
    }
}
~~~

Lệnh biên dịch và chạy bằng **JDK 21** từ thư mục chứa `src`:

~~~sh
javac --release 21 -encoding UTF-8 -Xlint:all -d out src/main/java/demo/PhaserCountsExample.java
java -cp out demo.PhaserCountsExample
~~~

**Stdout chính xác đã kiểm thử trong môi trường Windows với Java 21:**

~~~text
initial=phase=0,registered=1,arrived=0,unarrived=1
registration-phase=0
after-register=phase=0,registered=3,arrived=0,unarrived=3
workers-arrived=phase=0,registered=3,arrived=2,unarrived=1
main-next-phase=1
workers-next-phase=1,1
after-workers=phase=1,registered=1,arrived=0,unarrived=1
main-deregister-phase=1
terminated=true
phase-negative=true
~~~

### 8.1. Giải thích từng dòng và bất biến kiểm tra

| Dòng | Giải thích |
| --- | --- |
| `initial=phase=0,registered=1,arrived=0,unarrived=1` | Coordinator main đã đăng ký, chưa đến |
| `registration-phase=0` | `bulkRegister(2)` áp dụng vào phase 0, không advance |
| `after-register=phase=0,registered=3,arrived=0,unarrived=3` | Main + hai workers, cả ba chưa arrival |
| `workers-arrived=phase=0,registered=3,arrived=2,unarrived=1` | Latch đã xác nhận hai worker arrive; main là bên cuối chưa đến |
| `main-next-phase=1` | Main arrival cuối và đợi; barrier advance sang phase 1 |
| `workers-next-phase=1,1` | Cả hai worker `awaitAdvance(0)` đã được giải phóng, mỗi worker thấy phase 1 |
| `after-workers=phase=1,registered=1,arrived=0,unarrived=1` | Hai workers đã `arriveAndDeregister` khỏi phase 1; main còn lại |
| `main-deregister-phase=1` | Main rút khỏi phase 1, hàm trả arrival phase 1 |
| `terminated=true` | Số registered về 0, `onAdvance` mặc định chấm dứt phaser |
| `phase-negative=true` | Sau termination, `getPhase()` âm theo contract; không giả định số âm cụ thể |

Đây là output cố ý **không in tên thread hoặc lịch thực thi**. Lúc hai worker đang arrival phase 0, main chưa arrival nên phase không thể tự tiến; sau `Future.get` hai worker đã rút, nên counts ổn định trước khi main rút. Trong một chương trình thật không có các điểm phối hợp này, những getter có thể thay đổi ngay lập tức.

### 8.2. Vì sao `CountDownLatch` có trong ví dụ Phaser?

`CountDownLatch` chỉ giúp **main biết chính xác hai worker đã gọi `arrive()`** trước khi đọc snapshot. Nó **không thay thế barrier Phaser**. Chính `Phaser` mới điều khiển việc worker chỉ được đi tiếp khi main cũng đến.

Đây là một lựa chọn phục vụ test quyết định. Trong ứng dụng thực tế, không cần kèm thêm latch vào mọi Phaser; chỉ dùng latch khi thật sự cần sự kiện “đã tới điểm quan sát”.

### 8.3. Vì sao worker dùng `arrive() + awaitAdvance()`?

Tách hai bước giúp worker:

~~~java
int arrivalPhase = phaser.arrive();
bothArrived.countDown();
int nextPhase = phaser.awaitAdvance(arrivalPhase);
~~~

Thông báo cho main qua latch **sau** khi arrival đã được ghi nhận, rồi mới đợi phase chuyển. Nếu dùng `arriveAndAwaitAdvance()` trực tiếp, worker sẽ bị chặn tại barrier, không có điểm thông báo “đã đến” ở giữa để main kiểm chứng bộ đếm. Trong business code không cần quan sát count, `arriveAndAwaitAdvance()` thường gọn hơn.

### 8.4. Vì sao worker deregister ở phase 1 mà không ở phase 0?

Mỗi worker đã `arrive()` trong phase 0 và đợi advance. Khi phase chuyển sang 1, nó là một lượt mới; worker gọi `arriveAndDeregister()` **một lần cho phase 1**, vừa đến vừa rời barrier. Cách này **không làm double arrival trong cùng phase**.

Nếu worker gọi `arriveAndDeregister()` ngay sau `arrive()` trong phase 0, nó sẽ cố arrival hai lần cho một registration trong một phase, sai hợp đồng.

### 8.5. Vì sao không in các counts sau termination?

Javadoc `getArrivedParties` và `getUnarrivedParties` nói khi phaser terminated, những giá trị trả về **không mang ý nghĩa xác định**. Vì thế demo chỉ kiểm tra `isTerminated()==true` và dấu âm của `getPhase()`. Các counts sau termination không nên được dùng để đưa ra quyết định quản lý job.

### 8.6. Vì sao có `forceTermination()` trong `finally`?

Nếu một worker lỗi hoặc coordinator bị exception, bên còn lại có thể đang chờ `awaitAdvance`. `forceTermination()` khiến phaser vào trạng thái kết thúc và các waiter được giải phóng. Ví dụ có executor riêng được shutdown/awaitTermination để không để threads tồn tại ngoài vòng đời bài thử.

**Quan trọng:** `forceTermination()` **không tự interrupt/kill mọi worker** hoặc đảm bảo công việc nghiệp vụ được rollback. Worker phải có policy kiểm tra termination/error để không tiếp tục xử lý một bước đã bị hủy. Trong demo, cuối cùng executor cũng được dừng có giới hạn.

## 9. Phân biệt `arriveAndAwaitAdvance` với `awaitAdvance`

Hai phương thức dễ bị nhầm:

~~~java
// Party đã đăng ký, chưa đến ở phase hiện tại:
int next = phaser.arriveAndAwaitAdvance();

// Party đã gọi arrive() và có arrival phase p:
int next2 = phaser.awaitAdvance(p);
~~~

Trong dòng đầu, method **tự tính một lượt arrival** rồi chờ. Trong dòng sau, `awaitAdvance` **không tính một lượt arrival mới**; nó chỉ chờ phase đã cho thay đổi.

### 9.1. Người quan sát không đăng ký có chờ được không?

Theo API, `awaitAdvance(int)` có thể được **bất kỳ thread nào** sử dụng như một observer, với phase number phù hợp. Observer không cần tự là registered party vì method này không báo arrival.

Ngược lại, `arrive()`/`arriveAndAwaitAdvance()`/`arriveAndDeregister()` chỉ nên được gọi bởi **bên đã đăng ký**, vì chúng thay đổi nội bộ count. Phaser không kiểm tra danh tính thread; caller phải tự chịu trách nhiệm tính đúng.

### 9.2. `awaitAdvance(phase)` không chờ nhầm phase

~~~java
int observedPhase = phaser.getPhase();
int after = phaser.awaitAdvance(observedPhase);
~~~

Đây là ví dụ observer đơn giản, **có thể chờ vô hạn** nếu không còn bên nào làm phase tiến. Nếu phaser đã ở phase khác với argument khi gọi, method **trả về ngay**; đây là hành vi hữu ích để tránh bỏ sót tín hiệu advance xảy ra trước lúc bắt đầu chờ. Với production cần interruption/timeout, chọn overload interruptible.

### 9.3. Timeout và interruption

~~~java
int observed = phaser.getPhase();
try {
    int next = phaser.awaitAdvanceInterruptibly(
            observed, 5, TimeUnit.SECONDS);
    if (next < 0 || phaser.isTerminated()) {
        // Phaser đã kết thúc; không xử lý như một phase thành công.
    }
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    // Báo hủy/cleanup theo policy.
} catch (TimeoutException ex) {
    // Hết thời gian chờ; phaser KHÔNG tự deregister hoặc terminate.
}
~~~

Đây là **mã minh họa**, cần imports và quy trình xử lý nghiệp vụ đầy đủ. `awaitAdvanceInterruptibly` có checked `InterruptedException` và `TimeoutException`. Theo Javadoc, **timeout/interruption của lời chờ không tự thay đổi trạng thái phaser**. Nếu party đã đăng ký nhưng ngừng tham gia sau timeout, phải có **chính sách khôi phục** để tránh để các bên khác kẹt; trong nhiều lỗi bất ngờ có thể gọi `forceTermination()` để giải phóng tất cả waiters, rồi đóng/cancel jobs.

`awaitAdvance(int)` loại không interruptible **tiếp tục chờ ngay cả khi thread bị interrupt**; không dùng nó khi bắt buộc dừng nhanh theo interrupt mà không có một đường termination khác.

## 10. Termination và số đếm sau khi đã kết thúc

`Phaser` có thể terminated qua:

- `onAdvance(phase, registeredParties)` trả `true` khi chuẩn bị advance. Mặc định, nó trả true khi số parties về **0 do deregistration**.
- `forceTermination()` làm phaser kết thúc để giải phóng waiters, ví dụ khi pipeline fail.

### 10.1. Giá trị phase âm

Khi `isTerminated() == true`:

- `getPhase()` trả một giá trị **âm**.
- Các phương thức sync thường trả ngay một phase âm thay vì tiếp tục chờ.
- `register()/bulkRegister()` **không thêm party mới** và trả phase âm.
- Các counts `getArrivedParties()/getUnarrivedParties()` là **không có ý nghĩa bảo đảm**; đừng dùng để ước lượng tiến độ sau termination.
- `forceTermination()` gọi lặp khi đã terminated không có hiệu ứng mới; nó không làm số registered tự trở về 0.

**Không coi phase âm là “phase -1” theo nghĩa thứ tự nghiệp vụ:** dấu âm mã hóa trạng thái termination. Nếu cần xử lý nguyên nhân kết thúc (thành công, timeout, lỗi task), ứng dụng phải quản lý trạng thái/exception riêng; `Phaser` không chứa một business-result object.

### 10.2. Override `onAdvance` khi có số vòng cố định

Có thể dừng phaser khi đã hoàn tất N vòng:

~~~java
Phaser phaser = new Phaser(3) {
    @Override
    protected boolean onAdvance(int phase, int registeredParties) {
        return phase >= 4 || registeredParties == 0;
    }
};
~~~

Đây là **mã minh họa**: tại phase 0,1,2,3,4, các parties còn đăng ký arrival đủ; lần cuối tương ứng phase 4 làm hook trả true, kết thúc sau **5 vòng**. Vì đây là anonymous subclass trong Java, cần imports và các party phải phối hợp đủ lượt; đừng gọi arrival từ party chưa đăng ký. Không làm công việc blocking nặng trong `onAdvance`, vì hook được gọi bởi party đang kích hoạt transition và có thể cản trở những threads đang chờ.

### 10.3. Có nên gọi `getUnarrivedParties()==0` để quyết định dừng?

Không. Không có hợp đồng rằng ứng dụng sẽ kịp quan sát 0 giữa lượt arrival cuối và transition; có thể chuyển phase trước khi caller đọc. Nếu muốn dừng theo N rounds, dùng `onAdvance` hoặc một coordinator có phase-aware state, không spin trên getters.

## 11. Dùng Phaser trong quy trình xử lý nhiều bước

Ví dụ pipeline gồm ba tác vụ: phân tích dữ liệu, biến đổi, đối soát. Mỗi round gồm những task phối hợp tại một điểm:

~~~text
Phase 0:    worker A ... tính       -> arrive
            worker B ... tính       -> arrive
            worker C ... tính       -> arrive
                                     [ADVANCE]
Phase 1:    worker A ... xử lý tiếp -> arrive
            worker B ... xử lý tiếp -> arrive
            worker C ... xử lý tiếp -> arrive
                                     [ADVANCE]
Phase 2:    ...
~~~

Nếu tất cả parties ở mọi vòng đều cố định, mã:

~~~java
for (int round = 0; round < 3; round++) {
    performIndependentStep(round);
    int nextPhase = phaser.arriveAndAwaitAdvance();
    if (nextPhase < 0) {
        break; // Termination/abort.
    }
}
phaser.arriveAndDeregister();
~~~

Đây là **pseudocode Java minh họa**, cần `performIndependentStep` và registration của từng party, cũng như policy đảm bảo không gọi `arriveAndDeregister()` thừa sau khi đã terminate. Nó cho thấy điểm barrier đặt **sau công việc của từng vòng**.

Nếu một party có ít việc hơn, nó có thể deregister khi đến round cuối mà nó tham gia. Khi đó các vòng sau không chờ party đã rời đi. Nhưng thêm/rút party tùy ý ngay trong lúc phase đang advance cần được thiết kế để không làm thay đổi không mong đợi tập người phải chờ ở vòng tiếp theo.

### 11.1. Party đăng ký động khác thread sinh động

Một số ứng dụng tạo tasks mới trong runtime. `register` làm tăng barrier population, nhưng **không tự tạo hoặc chạy thread**. Ngược lại, khởi chạy một thread **không tự register vào Phaser**. Hai thao tác phải được điều phối:

- Register trước khi submit worker có trách nhiệm arrival.
- Nếu submit thất bại và worker chưa chạy, cần xử lý count đã đăng ký một cách đúng.
- Nếu worker hoàn tất/rút khỏi workflow, deregister đúng thời điểm.
- Không để một bên đăng ký nhưng không còn code nào có thể báo arrival, vì các bên khác sẽ chờ mãi.

Trong hệ thống có timeout/cancellation, nên xây lifecycle manager biết ai đã register, đang ở phase nào và có còn được phép arrive/deregister không. `Phaser` không cung cấp method `isRegistered(Thread)` hoặc tracking party IDs.

### 11.2. Thread pool không đủ capacity gây đình trệ

Nếu đăng ký 5 parties nhưng executor chỉ có 2 threads và hai workers đầu tiên gọi `arriveAndAwaitAdvance()` rồi block ở barrier, ba tasks còn lại chưa có thread để chạy thì có thể gặp starvation/deadlock ứng dụng. Phaser **không tự tăng pool size**. Với `ForkJoinPool`, có một số cơ chế phối hợp/compensation, nhưng vẫn phải thiết kế đủ khả năng tiến triển và không block bằng các locks/I/O ngoài kiểm soát.

Trong demo phần 8, executor có **2 threads** cho **2 workers**, còn main là party thứ ba và chạy trên thread riêng. Do đó mỗi registered party đều có đường thực thi tới barrier.

### 11.3. Memory consistency

Javadoc Phaser quy định các hành động trước một thao tác `arrive` xảy ra trước (**happen-before**) phase advance tương ứng và `onAdvance`, từ đó xảy ra trước các hành động sau phase advance. Đây là một lý do phaser là primitive đồng bộ thật, mạnh hơn polling một biến count không có happens-before rõ ràng.

Tuy vậy, bảo đảm visibility không giúp loại bỏ mọi race. Nếu nhiều workers **cùng ghi một phần tử trước barrier**, barrier không tự làm phép ghi ấy atomic/không xung đột. Chia dữ liệu theo vùng hoặc dùng synchronization đúng cho phần dữ liệu mutable.

## 12. Phaser so với CountDownLatch và CyclicBarrier

| Tiêu chí | `Phaser` | `CountDownLatch` | `CyclicBarrier` |
| --- | --- | --- | --- |
| Cơ chế | Barrier nhiều phase với số parties biến đổi | Đếm ngược tới 0, one-shot | Barrier tái sử dụng theo parties cố định |
| Số parties | `register`/`deregister` linh hoạt | Count cố định từ constructor, giảm về 0 | Số parties cố định khi tạo |
| Tái sử dụng nhiều vòng | Có | Không tự reset | Có |
| Đọc số vòng | `getPhase()` | Không có generation tương đương | Có `getNumberWaiting()` nhưng không tương đương phase ID |
| Đọc tổng parties | `getRegisteredParties()` | `getCount()` là đếm ngược, không phải registered parties | `getParties()` |
| Đếm chưa đến trong phase | `getUnarrivedParties()` | `getCount()` cho one-shot | Không có cùng bộ đếm unarrived public |
| Báo đến rồi rút | `arriveAndDeregister()` | Không có registration/deregistration | Không có dynamic deregistration |
| Kết thúc cưỡng bức | `forceTermination()` | Không có termination tương đương | `reset()` theo semantics broken barrier, khác Phaser |

**Không chọn Phaser chỉ vì có nhiều getters.** Chọn khi cần barrier nhiều phase và/hoặc số parties thay đổi. Nếu chỉ cần chờ một lần một số công việc cố định, `CountDownLatch` có thể đơn giản hơn. Nếu barrier nhiều vòng nhưng số parties cố định và policy xử lý broken barrier theo `CyclicBarrier` phù hợp, nó cũng là lựa chọn hợp lệ hiện hành.

## 13. Monitor metrics có ích nhưng không được trở thành race condition

Trong các bảng điều khiển vận hành, ta có thể log:

~~~java
System.out.printf(
    "phase=%d registered=%d arrived=%d unarrived=%d%n",
    phaser.getPhase(),
    phaser.getRegisteredParties(),
    phaser.getArrivedParties(),
    phaser.getUnarrivedParties());
~~~

Đây là đoạn minh họa monitoring. Những giá trị này có thể thay đổi ngay trong quá trình chuẩn bị lập chuỗi; đặc biệt nếu phase advance giữa hai getter calls, `registered=arrived+unarrived` **có thể không khớp trong chính dòng log**. Đây không tự chứng minh Phaser bị lỗi. Nếu cần một snapshot nhất quán tuyệt đối cho nghiệp vụ, thiết kế synchronization/state bên ngoài hoặc ghi nhận dữ liệu tại các điểm ổn định đã được phối hợp.

### 13.1. Khi nào snapshot hợp lệ để kiểm thử?

Bạn có thể kiểm thử các bộ đếm tại những **quãng thời gian đã bảo đảm không có thread nào thay đổi Phaser**:

- Trước khi khởi chạy workers, sau khi đăng ký đủ.
- Sau khi một `CountDownLatch` xác nhận workers đã `arrive`, nhưng một coordinator **chưa đến**, nên phase chưa thể advance và workers đang bị chặn.
- Sau khi các workers đã hoàn tất và deregister, nhưng coordinator còn chờ arrival ở phase mới.
- Sau một lời gọi đồng bộ đã bảo đảm phase hoàn tất, với điều kiện không có thread khác tiếp tục thay đổi registration/arrival cùng lúc.

Không dùng `Thread.sleep(100)` để “chắc chắn workers đã arrival”. Sleep không tạo ra bảo đảm dữ liệu/ordering cần thiết.

### 13.2. Khi nào nên log cả phase?

Nếu log chỉ ghi `unarrived=2`, người đọc không biết “còn hai parties của phase nào”. Ghép phase vào log sẽ giúp hiểu unarrived reset sau mỗi phase, nhưng vẫn là nhiều lời gọi getter không nguyên tử.

### 13.3. Getter trả số bằng 0 không cho biết tất cả workflow đã xong

`getRegisteredParties()==0` có thể chỉ ra hiện không có parties trên phaser, nhưng không chứng minh mọi business request trong hệ thống đã commit/flush hoặc không có task khác đang được submit. `Phaser` chỉ đồng bộ những **parties đã đăng ký**. Những công việc không đăng ký hoặc còn đang làm I/O ngoài phaser cần lifecycle tracking riêng.

## 14. Các lỗi phổ biến

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Hiểu `registered` là số OS threads | Party không gắn với identity thread trong API | Quản lý logical participants riêng |
| Hiểu `unarrived` là số task chưa chạy | Task có thể đã chạy, chỉ chưa báo đến | Đọc nó là số party chưa arrival |
| Hiểu `arrived=0` là chưa có ai làm việc | Phase có thể vừa advance và reset count | Xem phase và event lifecycle |
| Gọi `arrive()` hai lần cho một party một phase | Double arrival, vi phạm contract | Mỗi party arrival đúng một lần |
| Gọi `arrive()` rồi `arriveAndAwaitAdvance()` cùng phase | Tính hai lượt đến | Dùng `awaitAdvance(arrivalPhase)` sau arrive |
| Gọi `arriveAndDeregister()` sau arrive của cùng phase | Có thể double arrival | Deregister tại lượt đến đúng |
| Register rồi quên submit worker | Unarrived không thể về 0 | Phối hợp registration và submission/cleanup |
| Worker bị exception rồi không xử lý party còn đăng ký | Barrier treo | Error policy, có thể forceTermination |
| Đọc counts trong while loop để làm barrier | Getters chỉ dành cho monitoring | Dùng arrive/await |
| `getPhase()` được coi ID không bao giờ quay vòng | Có wrap tại `Integer.MAX_VALUE` | Không dùng làm unique ID vĩnh viễn |
| Phase âm vẫn được coi phase nghiệp vụ | Phase âm biểu thị termination | Kiểm tra `isTerminated` |
| Đọc `getUnarrivedParties` sau termination để quản lý cleanup | Value không còn ý nghĩa contract | State/lifecycle riêng |
| Timeout `awaitAdvanceInterruptibly` tự rút party | Timeout không đổi Phaser | Recovery và dereg/terminate đúng policy |
| Dùng `awaitAdvance()` khi bắt buộc interrupt | Method không interruptible | Chọn overload interruptible |
| Tạo nhiều workers hơn executor capacity, rồi tất cả block | Tasks chưa chạy không đến barrier được | Đảm bảo khả năng tiến triển |
| Override `onAdvance` làm I/O/block dài | Party cuối bị kẹt trong transition | Hook ngắn gọn |
| Nhầm `arrive()` return là next phase | Return là arrival phase | Dùng awaitAdvance hoặc getPhase theo ngữ cảnh |
| Nhầm `arriveAndAwaitAdvance()` return là arrival phase | Nó trả phase sau khi advance hoặc âm | Xử lý chính xác |
| Tưởng `register()` khởi chạy task | Nó chỉ tăng số đếm | Tự tạo/submit tasks |
| Thêm parties không giới hạn trên một Phaser | Có giới hạn tối đa 65535 parties | Tiered phasers hoặc thiết kế quy mô phù hợp |
| Dùng phase count thay transaction count | Phase không tương đương business outcome | Theo dõi job/results riêng |

## 15. Bài tập với đáp án

**Câu 1.** `new Phaser(4)` ban đầu có `getPhase/getRegistered/getArrived/getUnarrived` bằng bao nhiêu?  
**Đáp án:** `(0,4,0,4)`.

**Câu 2.** Nếu một party gọi `arrive()` từ trạng thái `(0,4,0,4)` và không có thao tác đồng thời, trạng thái mới?  
**Đáp án:** `(0,4,1,3)`.

**Câu 3.** Nếu ba bên còn lại lần lượt arrive, sau bên cuối trạng thái thường là gì?  
**Đáp án:** `(1,4,0,4)`, vì phase đã advance và arrived/unarrived reset cho vòng mới.

**Câu 4.** `getRegisteredParties()==4` nghĩa có đúng bốn Java threads đang chạy không?  
**Đáp án:** Không. Party là đăng ký logic, không có identity thread bên trong Phaser.

**Câu 5.** `getUnarrivedParties()==1` nghĩa gì?  
**Đáp án:** Còn một registered party chưa báo arrival của phase hiện tại tại thời điểm quan sát.

**Câu 6.** `getArrivedParties()==0` nghĩa chưa có worker nào từng đến không?  
**Đáp án:** Không. Có thể vừa bắt đầu phase mới, mọi lượt đến cũ đã được reset.

**Câu 7.** Tại sao `registered=arrived+unarrived` có thể không khớp trong log?  
**Đáp án:** Các getter đọc tại thời điểm khác nhau trong lúc phase/registration có thể chuyển; không là atomic snapshot.

**Câu 8.** Sự khác biệt giữa `register` và `arrive`?  
**Đáp án:** Register thêm bên chưa đến; arrive báo một bên đã đến. Chúng là hai hành động khác nhau.

**Câu 9.** `bulkRegister(3)` có tạo ba threads không?  
**Đáp án:** Không. Nó chỉ thêm ba registrations; ứng dụng tự submit ba tasks.

**Câu 10.** `arrive()` trả current/arrival phase hay next phase?  
**Đáp án:** Trả phase mà arrival áp dụng, có thể khác `getPhase()` sau khi arrival cuối gây advance.

**Câu 11.** `arriveAndAwaitAdvance()` trả gì?  
**Đáp án:** Phase sau advance hoặc phase âm khi terminated; nó vừa arrival vừa chờ.

**Câu 12.** `awaitAdvance(p)` có tính thêm một arrival không?  
**Đáp án:** Không. Nó chỉ chờ phase thay đổi khỏi `p` hoặc trả ngay nếu đã khác/terminated.

**Câu 13.** Khi nào `arriveAndDeregister` nên dùng?  
**Đáp án:** Khi party hoàn thành lượt đến và không cần được tính vào các phase sau, không gọi thêm nếu party đã arrival cùng phase.

**Câu 14.** Một party mới register lúc phase hiện tại còn chờ có thể khiến barrier chậm hơn không?  
**Đáp án:** Có. Nó tăng registered/unarrived cần được đáp ứng trước khi phase có thể advance.

**Câu 15.** `getPhase()<0` nghĩa gì?  
**Đáp án:** Phaser đã terminated; kiểm tra rõ bằng `isTerminated()`.

**Câu 16.** Có nên đọc `getUnarrivedParties` sau termination để biết còn ai chưa hoàn tất không?  
**Đáp án:** Không. Javadoc nói count ấy không còn ý nghĩa bảo đảm; cần state riêng.

**Câu 17.** Nếu `awaitAdvanceInterruptibly` bị timeout, phaser tự deregister chưa?  
**Đáp án:** Chưa. Timeout không thay đổi phaser; recovery phải được ứng dụng thiết kế.

**Câu 18.** `Phaser()` mặc định với 0 parties có terminated ngay không?  
**Đáp án:** Không, nó bắt đầu phase 0 và có thể `register` parties mới. Termination mặc định liên quan đến phase advance khi parties về 0 do deregistration.

**Câu 19.** Vì sao ví dụ dùng `CountDownLatch(2)` ngoài `Phaser`?  
**Đáp án:** Để main biết cả hai worker đã arrival trước khi chụp bộ đếm. Phaser vẫn là barrier quyết định tiến sang phase 1.

**Câu 20.** Trong demo, tại sao sau cả hai worker Futures hoàn tất `registered=1` mà không phải 3?  
**Đáp án:** Hai worker đã `arriveAndDeregister()` ở phase 1, chỉ main còn đăng ký.

**Câu 21.** Tại sao main cuối cùng thấy `phase-negative=true`?  
**Đáp án:** Main rút registration cuối cùng, default `onAdvance` làm phaser terminated; `getPhase` mang giá trị âm.

**Câu 22.** Một worker bị lỗi trước khi arrival, cần xử lý gì?  
**Đáp án:** Không để parties khác chờ vô hạn; có recovery policy, ví dụ forceTermination toàn phaser và báo lỗi ra workflow, đồng thời cleanup executor/resources.

**Câu 23.** `getRegisteredParties()` ở child phaser trong mô hình tree có phải tổng số mọi threads ở cả root và children không?  
**Đáp án:** Không. Nó phản ánh parties **đăng ký ở chính phaser đó**; một child có parties có thể được đăng ký như một party tại parent theo cơ chế tiered phaser.

**Câu 24.** Nếu `arriveAndAwaitAdvance()` được gọi khi không có lỗi, nó bảo đảm business task đã commit database chưa?  
**Đáp án:** Không. Nó chỉ bảo đảm những parties có tham gia barrier đã arrival theo đồng bộ; trạng thái transaction/IO cần cơ chế nghiệp vụ riêng.

## 16. Checklist khi áp dụng vào production

- [ ] Xác định rõ party là đơn vị nào (worker, task, phase participant), không nhầm với OS thread.
- [ ] Register đúng số lượng trước khi tasks đến barrier, có cleanup nếu submit thất bại.
- [ ] Mỗi party arrival **một lần mỗi phase**, không double arrival.
- [ ] Dùng `arriveAndAwaitAdvance` khi cần barrier, `arrive()+awaitAdvance` khi cần tách hai bước.
- [ ] Dùng `arriveAndDeregister` ở lượt arrival cuối mà party còn tham gia, không gọi bừa sau một arrival khác cùng phase.
- [ ] Không dùng `getUnarrivedParties`/`getArrivedParties` để thay synchronization; chỉ monitoring.
- [ ] Khi log counters, đi kèm phase và cảnh báo snapshot không nguyên tử.
- [ ] Không dựa vào `unarrived=0` để phát hiện phase advance.
- [ ] Xử lý phase âm/isTerminated trước khi tiếp tục logic nghiệp vụ.
- [ ] Không sử dụng counts sau termination để suy ra số jobs còn chạy.
- [ ] Có chiến lược timeout/interruption và fail-fast recovery; không để party mất tích vĩnh viễn.
- [ ] Dùng `awaitAdvanceInterruptibly` nếu chờ cần deadline/interrupt, biết timeout không tự sửa phaser.
- [ ] Cân nhắc executor capacity đủ cho số parties đồng thời có thể đang đợi barrier.
- [ ] Không block lâu trong `onAdvance` và không gọi các arrival/wait methods trong hook theo cách contract không xác định.
- [ ] Với nhiều parties, cân nhắc tree/tiered phasers và hiểu counts là local cho từng phaser.
- [ ] Không xem phase number là unique ID vĩnh viễn; lưu ý wrap khi lớn.
- [ ] Dùng snapshot/input ownership và synchronization phù hợp cho dữ liệu được chia sẻ; Phaser không sửa mọi data race.
- [ ] Có unit tests cho 0/1/n parties, register, arrive, deregister, timeout, termination và phase transition.
- [ ] Bảo vệ producer/consumer khỏi việc đăng ký task chưa chắc được chạy.
- [ ] Shutdown threads/executors do ứng dụng sở hữu, giải phóng waiters khi có lỗi.
- [ ] Chỉ sử dụng API Java `Phaser` hiện hành và hướng dẫn còn áp dụng trong JDK mới.

## 17. Tài liệu chính thức

- [Java SE 21 — Phaser](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Phaser.html): `getPhase`, `getRegisteredParties`, `getArrivedParties`, `getUnarrivedParties`; semantics registration/arrival, monitoring, termination, hook `onAdvance` và tiering.
- [Java SE 21 — CountDownLatch](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CountDownLatch.html): tín hiệu có thời điểm quan sát rõ trong ví dụ (không thay thế barrier chính).
- [Java SE 21 — ExecutorService](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html): submit worker tasks, `Future` và shutdown.
- [Java SE 21 — CyclicBarrier](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CyclicBarrier.html): đối chiếu reusable fixed-party barrier.
- [Java SE 21 — TimeUnit](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/TimeUnit.html): cấu hình thời hạn chờ/timeout.

**Kết luận:** `Phaser` quản lý một barrier tái sử dụng được bằng **phase number** và ba bộ đếm **registered / arrived / unarrived**. Trong một trạng thái ổn định, `registered = arrived + unarrived`; khi party cuối đến, phase tăng và bộ đếm arrivals bắt đầu lượt mới. `register` thêm bên phải chờ, `arrive` ghi nhận bên đến, `arriveAndDeregister` rút bên khỏi các vòng tiếp theo. **Các getters chỉ là dữ liệu quan sát**, không là tín hiệu chính xác để điều phối; hãy dùng `arriveAndAwaitAdvance` hoặc `awaitAdvance` để đồng bộ, và xử lý rõ termination/error trên Java hiện đại.
