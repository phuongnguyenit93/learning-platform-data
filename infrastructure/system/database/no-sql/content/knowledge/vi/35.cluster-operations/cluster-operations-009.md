# Đồng bộ thời gian và các giả định liên quan đến timestamp/lease

Trong một cụm **Database No SQL**, nhiều node ghi dữ liệu, sao chép log, hết hạn bản ghi, tranh quyền làm leader, xử lý retry và thực hiện các job nền. Những hành động này đều có thể dùng **thời gian**, nhưng không nhất thiết dùng cùng một loại đồng hồ hoặc có cùng bảo đảm. Nếu một node nhanh hơn 400 ms, một node chậm hơn 600 ms, hoặc hệ điều hành chỉnh đồng hồ lùi lại, các phép so sánh timestamp và thời hạn lease có thể tạo ra kết quả rất khác điều lập trình viên hình dung.

Ví dụ một tác vụ chỉ được một worker thực hiện tại một thời điểm:

~~~text
Worker A được cấp lease đến "10:00:10"
A tạm dừng vì GC hoặc mất kết nối
Lease của A hết hạn theo nguồn điều phối
Worker B nhận lease mới và bắt đầu ghi
A hoạt động trở lại, vẫn tưởng mình là owner
A cũng gửi một write tới NoSQL
~~~

Nếu database chỉ kiểm tra khóa có dạng chuỗi `owner=A` ở phía Java, hai worker có thể làm việc đồng thời. Việc cài NTP trên mọi host **không tự ngăn được một worker cũ tiếp tục ghi**. Thiết kế cần nêu rõ *ai quyết định lease còn hiệu lực*, *đồng hồ nào được dùng*, *độ sai lệch tối đa được chấp nhận* và *bản ghi đích có chặn được owner lỗi thời hay không*.

Bài thuộc chương **Vận hành cụm** của **Database No SQL**, trình bày một cách thực hành:

- **Wall clock, monotonic clock, logical clock và hybrid logical clock (HLC)** khác nhau thế nào.
- **NTP/chrony/PTP**, clock offset, skew, drift, step, slew, leap second và các giới hạn khi giám sát.
- Những giả định thời gian trong **timestamp ordering, last-write-wins, TTL, CDC, audit, replication và session consistency**.
- **Lease, leader election, distributed lock, fencing token, epoch/term và conditional write**; phân biệt timeout với bằng chứng an toàn.
- Ví dụ trong **Java**, **Cassandra**, **MongoDB**, **DynamoDB**, **Redis** và coordination stores như **etcd/ZooKeeper**.
- Cách kiểm thử clock jumps, network partitions, process pause và failover; cách xây monitoring, runbook và ngưỡng dừng an toàn.

Các con số và sơ đồ là **ví dụ tính toán**, không phải cam kết độ chính xác của NTP, KMS, một JVM hoặc một NoSQL engine cụ thể. Mỗi hệ có semantics riêng; phải dựa vào cấu hình và failure model thực tế khi dùng để giữ invariant quan trọng.

> **Nguyên tắc cốt lõi:** Đồng bộ thời gian giúp giảm sai lệch và hỗ trợ quan sát, nhưng **timestamp không tự là một transaction order**, **TTL không tự là distributed lock an toàn**, và **lease hết hạn không tự vô hiệu hóa mọi hành động từ chủ cũ**.

---

## 1. Vì sao vận hành cụm phải quan tâm đến thời gian?

Một node có thể dùng timestamp cho nhiều mục tiêu:

| Mục tiêu | Ví dụ | Sai giả định thường gặp |
|---|---|---|
| Hiển thị lịch sử | `createdAt`, `updatedAt` | Timestamp tăng thì mọi sự kiện xảy ra theo cùng thứ tự |
| Giải quyết xung đột | Last-write-wins | Đồng hồ nhanh luôn đại diện write mới hơn |
| Thời hạn dữ liệu | TTL, token expiration | Dữ liệu biến mất đúng thời điểm trên mọi node |
| Lease/leader | Owner còn hiệu lực đến thời điểm X | Mọi worker đồng ý chính xác khi nào X đến |
| Deadline | Request timeout 200 ms | `currentTimeMillis` không bao giờ nhảy |
| Replication/CDC | Commit-to-visible lag | Trừ hai timestamp khác host luôn cho số trễ đúng |
| Bảo mật | JWT `exp`, certificate validity | Mọi host có cùng giờ tuyệt đối |
| Audit | Log correlation | Có thể sắp log phân tán chỉ bằng timestamp |
| Scheduled jobs | Chạy lúc 02:00 | Không có giờ trùng/thiếu khi đổi múi giờ |
| DR | Recovery Point Objective | Snapshot wall time chính xác tương ứng commit order |

Điểm chung: mỗi use case đòi một **hợp đồng thời gian** khác nhau. “Có đồng bộ NTP” là điều kiện vận hành hữu ích, không phải câu trả lời cho tất cả những hàng trên.

## 2. Ba câu hỏi trước khi dùng timestamp

Bất kỳ thiết kế nào phụ thuộc thời gian cần trả lời:

1. **Nguồn thời gian là gì?** Đồng hồ hệ điều hành, monotonic JVM, database server, broker, consensus revision hay event-time do client gửi?
2. **Độ tin cậy được bảo đảm ra sao?** Offset/uncertainty có bound được giám sát không; có thể nhảy lùi/tiến; có vượt qua reboot hoặc region failure được không?
3. **Nếu giả định sai, điều gì bị phá?** Chỉ biểu đồ thời gian lệch vài giây, hay tạo duplicate payment, đánh mất write, vi phạm quyền truy cập hoặc có hai leaders?

Không ghi yêu cầu thành “clock luôn đúng”. Hãy ghi **tolerance và hành vi khi clock không đủ tin cậy**.

## 3. Wall clock: thời gian lịch

**Wall clock** biểu diễn thời điểm trên thang thời gian dân sự, thường bằng UTC epoch time hoặc `Instant` trong Java.

Ví dụ:

~~~text
2026-11-14T08:30:00Z
Unix epoch milliseconds: một số mili giây kể từ mốc epoch
~~~

Wall clock phù hợp cho:

- Ghi `createdAt`/`updatedAt` phục vụ hiển thị, báo cáo.
- Lịch chạy theo thời gian thực.
- Certificate/token validity theo thời điểm.
- Persistent expiration timestamps cần đọc qua restart.
- Audit correlation khi chấp nhận sai số đồng hồ.

Nhưng wall clock có thể được **điều chỉnh** bởi dịch vụ đồng bộ, quản trị viên hoặc môi trường ảo. Nó không phải công cụ mặc định để đo elapsed duration hoặc một chứng minh tổng thứ tự giao dịch.

## 4. UTC khác múi giờ hiển thị

UTC timestamp chỉ một thời điểm thống nhất; `Asia/Ho_Chi_Minh` là múi giờ dùng khi hiển thị và lập lịch theo địa phương.

Ví dụ:

~~~text
Instant:       2026-11-14T08:00:00Z
Local display: 2026-11-14 15:00:00 +07:00
~~~

Nên lưu thời điểm dạng `Instant`/epoch chuẩn, kèm business time zone khi lịch nghiệp vụ cần nó. Không lưu chuỗi `14/11/2026 15:00` rồi dùng để so thứ tự trên nhiều regions mà không biết offset.

**UTC không có nghĩa clock không sai.** Hai máy đều cấu hình UTC vẫn có thể lệch nhau nhiều giây.

## 5. Monotonic clock: đo khoảng thời gian

Một monotonic clock có mục đích cung cấp giá trị tiến theo hướng không giảm theo hợp đồng implementation, hữu ích để đo **elapsed time**.

Trong Java:

~~~java
long started = System.nanoTime();
try {
    executeDatabaseOperation();
} finally {
    long elapsedNanos = System.nanoTime() - started;
    recordLatency(elapsedNanos);
}
~~~

`System.nanoTime()` có mốc tham chiếu tùy JVM/implementation; **không phải UTC timestamp**. Nó được dùng cho *hiệu hai lần đọc trong cùng context phù hợp*, không lưu thành `updatedAt` và không so trực tiếp giữa hai hosts.

Một số monotonic clocks có tốc độ được điều chỉnh nhẹ để đồng bộ tần số; “monotonic” không có nghĩa thời gian trôi chính xác tuyệt đối tới từng nanosecond.

## 6. Vì sao không đo timeout bằng `currentTimeMillis`?

Đoạn code:

~~~java
long started = System.currentTimeMillis();
callDatabase();
long elapsed = System.currentTimeMillis() - started;
~~~

có thể bị ảnh hưởng nếu wall clock nhảy trong lúc operation đang chạy.

Ví dụ:

~~~text
Wall clock trước sync: 12:00:00.500
NTP/admin steps back: 12:00:00.000
Operation thật mất 100 ms
Measured elapsed có thể âm
~~~

Với timeout, rate measurement hoặc benchmark, dùng monotonic elapsed (`System.nanoTime()`, `Duration` từ timer thích hợp). Với **thời điểm trên lịch và bản ghi persisted**, dùng `Instant` và giải thích độ chính xác.

## 7. Monotonic clock không thay timestamp persistent

Giá trị `System.nanoTime()`:

- Không có mốc UTC có thể chia sẻ.
- Không hứa ổn định qua restart JVM.
- Không dùng để so giữa nodes.
- Không thích hợp ghi vào database làm lease expiry toàn cục.
- Không tự ngăn process pause, network delay hay deadlock.
- Trong môi trường OS/VM khác nhau có semantics về suspend/clock nguồn cần xác minh.

Do đó, có thể dùng nó để **worker tự giới hạn thời gian thực thi**, nhưng không đưa `nanoTime` của Worker A cho Worker B rồi yêu cầu B so theo đồng hồ của mình.

## 8. Ba đại lượng: offset, skew và drift

Trong ngữ cảnh vận hành đồng hồ:

- **Offset:** độ lệch giữa clock của một node và nguồn tham chiếu tại một thời điểm.
- **Clock skew:** độ lệch tương đối giữa hai clocks, hoặc sự khác biệt quan sát được của timestamp, tùy tài liệu.
- **Drift/rate error:** tốc độ đồng hồ đi nhanh/chậm so với thời gian tham chiếu; thường biểu diễn bằng parts per million (*ppm*).
- **Jitter:** biến động ngắn hạn của phép đo thời gian/offset, chịu ảnh hưởng mạng và scheduler.
- **Uncertainty:** giới hạn tin cậy về độ sai lệch thực, gồm measurement error, path asymmetry, clock quality và thời gian từ lần sync.

Tách những khái niệm này khi báo cáo. “NTP offset = 5 ms” không đồng nghĩa **mọi timestamp chỉ sai tối đa 5 ms**.

## 9. Skew giữa hai hosts có thể lớn hơn offset mỗi host

Giả sử nguồn tham chiếu là \(t\).

~~~text
Node A clock = t + 80 ms
Node B clock = t - 90 ms
~~~

Mỗi node lệch tham chiếu dưới 100 ms, nhưng:

\[
|C_A-C_B|=|80-(-90)|=170\text{ ms}
\]

Nếu từng node chỉ biết bound \(\pm\epsilon\) từ UTC, pairwise skew có thể gần **\(2\epsilon\)**.

Quy tắc tổng quát:

\[
|C_A-C_B|\le \epsilon_A+\epsilon_B
\]

với điều kiện \(\epsilon_A,\epsilon_B\) thực sự là các **upper bounds đã được chứng minh** trong failure model. Không dùng last measured offset như một bound tuyệt đối không có margin.

## 10. Drift theo ppm: ví dụ tính toán

Nếu một clock có sai tốc độ tối đa giả định \(d\) ppm và không được hiệu chỉnh trong \(T\) giây, sai lệch tăng thêm theo mô hình gần đúng:

\[
\Delta t_{\text{drift}}\lesssim \frac{d}{10^6}T
\]

Ví dụ \(d=50\text{ ppm}\), \(T=600\text{ s}\):

\[
\Delta t\lesssim\frac{50}{10^6}\times600
=0.03\text{ s}=30\text{ ms}
\]

Nếu offset tại lần đồng bộ đáng tin gần nhất có bound 60 ms, mô hình sai số sau mười phút có thể cần budget ít nhất **90 ms**, cộng thêm uncertainty khác.

Đây là **bài toán giả định có bound**, không khẳng định mọi máy có drift tối đa 50 ppm.

## 11. Sai số có thể tích lũy khi mất time source

Một node mất NTP:

~~~text
Last reliable bound: 20 ms
Assumed maximum drift: 100 ppm
Time without sync: 1 hour
```

Phần drift tăng thêm:

\[
3600\times 100/10^6=0.36\text{ s}
\]

Bound tổng có thể lớn tới khoảng 380 ms, trước các sai số khác.

Nếu ứng dụng giả định skew luôn dưới 100 ms để quyết định lease, node này không nên tiếp tục dựa vào giả định ấy. Khi mất nguồn đồng bộ, **safety policy có thể yêu cầu dừng những hành động phụ thuộc bound**.

## 12. Offset đo được không phải bound chắc chắn

Các phép đo thời gian trên mạng chịu ảnh hưởng:

- Network latency và path asymmetry.
- Queueing ở switch/host/VM.
- CPU scheduling và interrupt delays.
- Time source accuracy.
- Chất lượng thiết bị clock/oscillator.
- Leap handling.
- Số nguồn và đồng thuận giữa nguồn.
- Các bước hiệu chỉnh chưa hoàn tất.

Một dashboard chỉ hiển thị `last_offset=2ms` mà không có `root dispersion`, status/source health hoặc bound uncertainty có thể quá lạc quan.

## 13. Clock step là gì?

**Step** là chỉnh giá trị wall clock nhảy một đoạn ngay lập tức, ví dụ từ 12:00:10 về 12:00:07 hoặc nhảy lên 12:00:15.

Điều này có thể xảy ra khi:

- Host boot sau khi clock sai lớn.
- Admin thực hiện `date`/time set.
- Time synchronization service quyết định cho phép step.
- VM time restoration/migration gây clock discontinuity.

Tác động:

- Logs có timestamps đi lùi.
- Scheduler có thể chạy lệch.
- TTL kiểm bằng wall time có thể hết hạn quá sớm/muộn.
- Client-side `now < leaseUntil` có thể sai.
- Latency đo bằng wall clock trở nên vô nghĩa.

## 14. Clock slew là gì?

**Slew** điều chỉnh tốc độ trôi của đồng hồ dần dần để tiến gần nguồn tham chiếu thay vì nhảy tức thì.

Lợi ích:

- Hạn chế timestamp discontinuity.
- Phù hợp workloads nhạy với wall-time jumps.

Giới hạn:

- Trong giai đoạn correction, tốc độ thời gian không nhất thiết đúng tuyệt đối.
- Offset lớn có thể cần lâu để hội tụ.
- Cấu hình từng daemon/OS khác nhau.
- Monotonic clock vẫn có thể bị rate adjustment theo implementation.
- Slew không tạo total order hoặc bound mạnh nếu nguồn tham chiếu không tin cậy.

Đừng suy từ “không step” rằng lease có thể dùng wall clock mà không cần fencing.

## 15. Leap second và leap smear

Thời gian UTC có **leap seconds** theo hệ thống thang thời gian và công bố phù hợp; môi trường vận hành có thể xử lý bằng pause, step hoặc **leap smear** tùy provider/time source.

Nguy cơ:

- Hai hosts dùng chính sách khác nhau có timestamp lệch quanh thời điểm leap.
- Job lịch chạy sai giả định.
- Metric delta có giá trị bất thường.
- Distributed logs bị đảo thứ tự theo wall time.

Không mix time sources có leap-handling khác nhau mà không đánh giá. Cần thống nhất time policy trong cluster hoặc ít nhất kiểm thử hệ có thể chịu uncertainty.

## 16. NTP làm được gì?

**Network Time Protocol (NTP)** giúp hosts đồng bộ wall clocks với time servers qua network. Một daemon như **chronyd** có thể:

- So sánh nhiều time sources.
- Ước lượng offset và frequency error.
- Slew clock để điều chỉnh.
- Đánh giá source selection và trạng thái sync.
- Tiếp tục holdover khi mất nguồn theo khả năng.

NTP rất hữu ích cho logs, authentication, leases có bound được thiết kế, và vận hành. Tuy nhiên **NTP không phải giao thức đồng thuận database** và không thể bảo đảm mọi node nhận cùng “tick” đồng thời.

## 17. Thiết kế nguồn thời gian cho cluster

Ví dụ một topology:

~~~mermaid
flowchart TD
    Ref["Trusted time references"] --> T1["Time source A"]
    Ref --> T2["Time source B"]
    T1 --> H1["Database node 1 chrony"]
    T2 --> H1
    T1 --> H2["Database node 2 chrony"]
    T2 --> H2
    T1 --> H3["Java worker node chrony"]
    T2 --> H3
    H1 --> DB["NoSQL cluster"]
    H2 --> DB
    H3 --> API["Java application"]
~~~

Thực tế có thể dùng cloud-provided time service hoặc hệ phân cấp được quản trị. Các điểm cần đánh giá:

- Một hay nhiều nguồn đáng tin?
- Nguồn có độc lập thực sự không?
- Các nodes/AZ/regions có thể truy cập không?
- Time source có authenticated/protected khi threat model cần?
- Nguồn dự phòng có leap smear policy giống nhau?
- Có cảnh báo khi mất sync hay chuyển nguồn?
- Khi không có đủ nguồn, node sẽ **holdover, degrade hay stop**?

## 18. Chrony, ntpd và PTP khác nhau ra sao?

| Cơ chế | Phù hợp | Giới hạn cần lưu ý |
|---|---|---|
| NTP với chrony/ntpd | Server clocks qua IP network | Network asymmetry, daemon config, clock source |
| PTP (Precision Time Protocol) | Một số mạng có hardware timestamp và topology hỗ trợ | Hạ tầng/switch/NIC/clock design phức tạp |
| Cloud time service | Đồng bộ được quản lý trong cloud environment | Phụ thuộc provider/region/quy tắc leap |
| Local monotonic clock | Duration/deadline trong process | Không phải UTC và không so qua hosts |
| Logical/HLC | Ordering/causality metadata | Không thay đồng bộ clock cho mọi mục tiêu lịch |

PTP có thể đạt độ chính xác cao trong môi trường được thiết kế phù hợp, nhưng **không có nghĩa ứng dụng NoSQL tự có strong consistency**.

## 19. PTP không thay consensus

Ngay cả nếu tất cả hosts đồng bộ clocks ở microsecond scale, hai writers vẫn có thể:

- Ghi đồng thời vào hai partitions.
- Không nhìn thấy write của nhau do network partition.
- Thực hiện conditional updates sai.
- Đọc follower stale.
- Có transaction conflicts.
- Mất acknowledgment.

**Clock precision và distributed coordination là hai trục khác nhau.** Đừng dùng PTP làm lý do bỏ CAS/quorum/leader election khi domain yêu cầu exclusive ownership.

## 20. Bảo vệ time sources khỏi tấn công

Nếu attacker điều khiển time source hoặc giả mạo NTP traffic, họ có thể tác động:

- Token/certificate validity.
- Scheduler và audit timestamps.
- TTL/lease expiration nếu thiết kế phụ thuộc wall clock.
- Log correlation và forensic evidence.

Các biện pháp có thể gồm:

- NTP nguồn được phê duyệt/allowlist.
- Network isolation và hạn chế UDP traffic theo kiến trúc.
- Authentication cơ chế như **NTS** nếu được hỗ trợ/phù hợp.
- Giới hạn quyền thay đổi system clock.
- Phân tách privileged roles.
- Monitor unexpected time jumps và source switches.
- Tích hợp host hardening với security monitoring.

NTS bảo vệ một số nguy cơ giả mạo time exchange, **không bảo đảm mọi node có thời gian tuyệt đối chính xác** khi nguồn hoặc hạ tầng lỗi.

## 21. Kiểm tra chrony trên Linux

Các lệnh quan sát thường dùng:

~~~bash
chronyc tracking
chronyc sources -v
chronyc sourcestats -v
timedatectl status
date -u
~~~

`chronyc tracking` có thể hiển thị các trường như:

- Reference ID/source.
- System time và last offset.
- RMS offset.
- Frequency/residual frequency.
- Skew.
- Root delay/dispersion.
- Leap status.

Cần đọc ý nghĩa từng trường theo phiên bản chrony; **không lấy một giá trị last offset đơn lẻ làm bound tuyệt đối**. Lệnh `date -u` chỉ cho biết wall time hiện được báo, không chứng minh clock đã sync.

## 22. Không tùy tiện ép `makestep` trên production

Chrony có khả năng step clock theo cấu hình/lệnh phù hợp. Một thao tác step mạnh trong cluster đang chạy có thể ảnh hưởng:

- Lease checks dựa wall time.
- Expiration logic ở application.
- Scheduled jobs.
- Log ordering.
- Token validity.
- Timestamp conflict resolution.

Khi clock lệch nghiêm trọng, hãy theo **runbook của hệ điều hành/database**, đánh giá safety của services và maintenance window. Không tự chạy sửa giờ bằng tay để xóa alert khi chưa biết ứng dụng đang phụ thuộc vào clock thế nào.

## 23. Kiểm tra NTP trên Windows

Trong hạ tầng có Windows nodes, lệnh quan sát thường dùng:

~~~powershell
w32tm /query /status
w32tm /query /peers
w32tm /stripchart /computer:time.example.invalid /samples:5 /dataonly
~~~

Hostname `time.example.invalid` là placeholder; thay bằng approved time source. Các dòng lệnh này là **hướng dẫn quan sát**, không phải recipe bắt buộc cho mọi Windows/Active Directory setup.

Nếu cluster chạy trên Windows/Linux kết hợp, cần thống nhất time-source trust và nhận thức rõ mức sai lệch giữa các hệ.

## 24. Container và host clock

Một Java container thường sử dụng thời gian do host kernel/VM cung cấp theo environment, không có một NTP daemon riêng biệt có thể độc lập sửa đồng hồ cho toàn container trong mọi cấu hình.

Do đó:

- Kiểm clock trên **host/node**, không chỉ trong pod.
- Kiểm node pool/VM image và cloud time service.
- Không giả định restart pod sửa được clock drift của host.
- Nếu một Kubernetes node clock sai, nhiều pods trên node có thể cùng gặp lỗi.
- Trong môi trường hỗ trợ time namespaces/virtualization, phải biết semantics thực.

Một application metric hiển thị wall time sai có thể là triệu chứng của **underlying host**, không chỉ JVM.

## 25. Múi giờ và DST không phải skew

Một host hiển thị `UTC` và một host hiển thị `UTC+7` có thể cùng biểu diễn một thời điểm, **không phải lệch bảy giờ** nếu timestamp có offset đầy đủ.

Sai sót phổ biến:

~~~text
Node A stores "2026-11-14 08:00:00" (UTC)
Node B parses it as "2026-11-14 08:00:00" (local +07)
~~~

Kết quả bị diễn giải lệch bảy giờ dù clocks chạy đúng.

Trong Java:

- Dùng `Instant` cho timestamp tuyệt đối.
- Dùng `ZonedDateTime` cho lịch nghiệp vụ gắn múi giờ.
- Định nghĩa serialization theo ISO 8601/UTC.
- Không dựa vào default JVM time zone để parse payload không có zone.

## 26. Java: tách thời điểm và độ dài

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.Duration;

public final class AuditClock {
    private final Clock wallClock;

    public AuditClock(Clock wallClock) {
        this.wallClock = wallClock;
    }

    public Instant eventRecordedAt() {
        return wallClock.instant();
    }

    public Duration measureTask(Runnable task) {
        long started = System.nanoTime();
        task.run();
        return Duration.ofNanos(System.nanoTime() - started);
    }
}
~~~

`Clock` là abstraction hữu ích để inject thời gian cho business tests. `System.nanoTime()` dùng để đo elapsed duration của một lần xử lý. Ví dụ này cố tình không nuốt exceptions; production instrumentation nên ghi duration trong `finally` nếu cần bao phủ cả thất bại.

## 27. Java: deadline bằng monotonic elapsed

Một cách tránh wall time step khi điều khiển timeout cục bộ:

~~~java
import java.time.Duration;

public final class LocalDeadline {
    private final long startNanos = System.nanoTime();
    private final long timeoutNanos;

    public LocalDeadline(Duration timeout) {
        if (timeout.isNegative() || timeout.isZero()) {
            throw new IllegalArgumentException("timeout must be > 0");
        }
        timeoutNanos = timeout.toNanos();
    }

    public boolean expired() {
        return System.nanoTime() - startNanos >= timeoutNanos;
    }
}
~~~

Cần giới hạn timeout hợp lý và xét overflow/cancellation. Class này dùng **trong một process** để quản lý deadline, không phải distributed lease hay persistent expiry; restart làm mất trạng thái local.

## 28. Clock jumps và scheduled jobs

Nếu một scheduler chạy theo wall time:

~~~text
Every day at 02:30 local time
```

Ở vùng có daylight saving time, có ngày 02:30 không tồn tại hoặc lặp lại. Dù hệ chạy ở Việt Nam không đổi DST hiện tại, một cluster đa region vẫn có tenants ở những múi giờ khác.

Phải định nghĩa:

- Chạy theo UTC hay local business zone?
- DST gap/overlap policy.
- Job idempotency.
- Misfire/recovery handling.
- Chạy một lần mỗi lịch hay đúng mỗi 24 giờ?
- Khi clock steps forward/backward thì làm gì?

Scheduled job cần **durable execution record/idempotency**, không chỉ so `now == scheduledTime`.

---

## 29. Timestamp không tự biểu diễn quan hệ nhân quả

Giả sử hai nodes độc lập:

~~~text
Node A records Event X at local 10:00:01.200
Node B records Event Y at local 10:00:01.100
~~~

Không thể kết luận Y xảy ra trước X theo quan hệ nhân quả nếu clocks không có bound đủ mạnh và không biết network/transaction order.

Ngay cả khi Y có timestamp nhỏ hơn, X vẫn có thể được commit trước tùy clock skew. Khi cần ordering, hãy dùng **sequence/version/transaction log position/consensus term** theo scope.

## 30. Thứ tự wall-time khác commit order

Một write có thể bắt đầu trước nhưng commit sau:

~~~text
Request A starts at 10:00:00.000
Request B starts at 10:00:00.050
B commits at 10:00:00.080
A commits at 10:00:00.200
```

Nếu lưu `requestedAt`, timestamp A nhỏ hơn B; nếu cần **commit order** thì B đến trước A. Không dùng `requestedAt` để suy ai là write committed mới nhất.

Một timestamp được tạo ở **coordinator** khác với một timestamp được tạo ở **source commit protocol**.

## 31. Event-time khác processing-time

Một event CDC:

~~~json
{
  "eventId": "E100",
  "eventTime": "2026-11-14T08:00:00Z",
  "publishedAt": "2026-11-14T08:00:03Z",
  "processedAt": "2026-11-14T08:02:10Z",
  "aggregateVersion": 41
}
~~~

Đây là các ngữ nghĩa khác nhau:

- `eventTime`: lúc sự kiện nghiệp vụ được gán thời gian.
- `publishedAt`: lúc được gửi/broker tiếp nhận tùy contract.
- `processedAt`: lúc consumer xử lý.
- `aggregateVersion`: thứ tự state của aggregate theo nguồn có thẩm quyền.

Consumer có thể nhận E41 sau E42 và vẫn phải từ chối ghi state cũ vào current projection. **Event đến muộn theo time không luôn là state stale**; analytics có thể cần cộng nó vào cửa sổ lịch sử.

## 32. Broker timestamp và offset

Kafka có thể có timestamp với semantics như producer-created time hoặc broker log-append time theo cấu hình. Trong khi đó, **offset** xác định vị trí record trong một partition.

~~~text
Partition 0:
  offset 99  -> Product A v10
  offset 100 -> Product B v20
  offset 101 -> Product A v11
~~~

Offset đảm bảo một thứ tự trong log partition; không tự là timestamp UTC hay version của Product. Không so offset giữa partitions như một global sequence.

Khi cần audit/business ordering, ghi rõ nguồn timestamp và ordering scope thay vì dùng `System.currentTimeMillis()` ở consumer khi event đến.

## 33. ObjectId timestamp không là total order của MongoDB

MongoDB ObjectId có phần timestamp theo đặc tả ObjectId, thường ở độ phân giải giây, cùng những phần khác để tạo identifier. Nó không phải **transaction commit timestamp** có thể so tuyệt đối giữa mọi producers.

Hai documents tạo trong cùng giây có thể có ObjectIds khác theo process/random/counter; clock skew giữa clients còn ảnh hưởng thứ tự phần timestamp.

Không dùng:

~~~text
ObjectId lớn hơn => business write đã commit sau
```

làm invariant. Nếu cần per-entity version, tăng một field `version` atomically tại source.

## 34. UUIDv7/ULID giúp sắp xếp gần thời gian, không tạo consensus

Một số ID formats đưa thành phần thời gian vào identifier để hỗ trợ locality/sort gần theo thời gian.

Nhưng:

- Clock skew có thể làm identifiers đảo trật tự.
- Concurrent writers có cùng time bucket.
- Monotonic-generation rules chỉ có scope riêng.
- ID creation time khác commit time.
- Distributed conflicts không được giải quyết bằng sort theo ID.

Dùng time-sortable IDs cho access pattern nếu phù hợp, **không dùng làm bằng chứng linearizability**.

## 35. Lamport clock: thứ tự logic

Một **Lamport logical clock** tăng counter khi có local event và cập nhật khi nhận message để phản ánh quan hệ *happens-before*.

Tính chất quan trọng:

\[
a\rightarrow b \;\Rightarrow\; L(a)<L(b)
\]

Nhưng chiều ngược lại **không đúng**: \(L(a)<L(b)\) không chứng minh a gây ra b.

Có thể tie-break bằng node ID để có total ordering được định nghĩa, nhưng total order ấy không tự là physical-time order hoặc consensus commit order.

## 36. Vector clocks: theo dõi concurrency

**Vector clock** có thể phân biệt một số quan hệ causality:

- \(V_a<V_b\) theo thành phần → a precedes b.
- Hai vectors không so được → concurrent trong mô hình.

Đánh đổi:

- Metadata có thể tăng theo số actors.
- Membership changes cần xử lý.
- Merge/conflict policy vẫn thuộc domain.
- Không biến mọi concurrent updates thành state duy nhất đúng.

Một số NoSQL systems dùng causal metadata hoặc phiên bản biến thể; không tự giả định Vector Clock chuẩn tồn tại ở mọi API.

## 37. Hybrid Logical Clock (HLC)

HLC kết hợp thành phần thời gian vật lý với logic counter để giữ thông tin ordering theo message causality trong một mô hình được thiết kế.

Minh họa:

~~~text
HLC = (physicalComponent, logicalCounter)
Write A: (1000, 0)
Receive causal event at similar physical time:
Write B: (1000, 1)
```

HLC có thể giúp thiết kế timestamp có ordering hữu ích mà không phụ thuộc hoàn toàn vào đồng hồ vật lý tuyệt đối.

Nhưng:

- HLC **không tự là consensus**.
- HLC không tạo lock/lease an toàn nếu các assumptions bị bỏ qua.
- Causal/event timestamp không tự đảm bảo toàn bộ multi-key transaction serializable.
- Một số hệ dùng uncertainty windows, commit-wait hoặc giới hạn maximum offset theo protocol riêng.

Không tự thêm HLC vào ứng dụng rồi tuyên bố reads linearizable.

## 38. Timestamp oracle và consensus ordering

Một số cơ sở dữ liệu có cơ chế phát **transaction timestamp** từ một authority/coordinator, hoặc dùng thuật toán đồng thuận kết hợp physical clock uncertainty. Những bảo đảm cụ thể phụ thuộc hệ và giao thức.

Điểm khác biệt quan trọng:

~~~text
Local wall clock timestamp:
  independent value from one host

Commit sequence/term:
  agreed ordering or log position within a scope

HLC/transaction timestamp:
  ordering metadata under protocol-defined assumptions
```

Không tự lấy epoch milliseconds do Java tạo làm bản sao của một **globally ordered commit timestamp** từ database.

## 39. Timestamp uncertainty là một khoảng, không luôn là điểm

Nếu một time service có thể cung cấp hoặc hệ vận hành đặt bound \(\pm\epsilon\), thời gian thực có thể nằm trong khoảng:

\[
t_{\text{real}}\in[C_i(t)-\epsilon_i,\;C_i(t)+\epsilon_i]
\]

Khi hai intervals của events chồng nhau, chỉ dùng physical clock readings thường không xác định được thứ tự tuyệt đối.

Một số database protocols cố ý chờ hoặc dùng uncertainty handling để đạt external consistency theo bảo đảm của chúng. **Không tổng quát hóa một implementation cụ thể thành tính chất của NTP thông thường**.

## 40. Last-write-wins cần hỏi “last” theo đồng hồ nào

Các định nghĩa “last” khác nhau:

- Request được client phát sau.
- Database nhận request sau.
- Transaction commit sau.
- Timestamp lớn hơn.
- Source aggregate version lớn hơn.
- Event đến consumer sau.
- Conflict policy chọn winner sau.

Nếu storage engine dùng **last-write-wins dựa timestamp**, write có clock nhanh có thể thắng write xảy ra muộn hơn. Đây là một *conflict resolution policy*, không là bằng chứng write mới hơn về nghiệp vụ.

## 41. Ví dụ write bị lấn bởi clock lệch

~~~text
Real time t=100s:
  Node A clock=105s
  A writes status=PENDING with timestamp 105

Real time t=102s:
  Node B clock=101s
  B writes status=PAID with timestamp 101
```

Nếu hệ chọn giá trị có timestamp lớn hơn, `PENDING` có thể thắng `PAID` dù B ghi sau theo thời gian thực.

Không sửa bằng cách tăng retry hoặc thêm replicas. Cần **clock discipline** và quan trọng hơn là **business ordering/CAS/transaction** cho state transitions không được phép đi lùi.

## 42. Cassandra: timestamp dùng trong reconciliation

Apache Cassandra dùng timestamps để phân giải nhiều mutations theo cơ chế reconciliation của engine, trong đó **write timestamp** có vai trò quan trọng trong last-write-wins ở granularity thích hợp.

Nguồn timestamp có thể do client/driver hoặc server/coordinator theo API và cấu hình. Sai lệch thời gian giữa producers/coordinators có thể ảnh hưởng winner của conflicting writes.

Các lưu ý:

- Timestamps không tự là linearizable commit order.
- Một write với timestamp nằm quá xa tương lai có thể che writes sau có timestamp nhỏ hơn.
- LWT/conditional writes có semantics riêng, không trộn tùy tiện với unrestricted client timestamps.
- Tombstone/TTL và repair/compaction có quan hệ với thời gian.
- Clock synchronization chỉ giảm rủi ro; business invariants vẫn cần primitive phù hợp.

## 43. Cassandra CQL: timestamp và TTL

Một ví dụ CQL (minh họa capability theo ngữ cảnh):

~~~sql
INSERT INTO product_status (
    tenant_id, product_id, status
) VALUES (
    't17', 'p101', 'ACTIVE'
) USING TIMESTAMP 1794650000000000;

UPDATE session_cache
USING TTL 600
SET payload = '...'
WHERE tenant_id = 't17'
  AND session_id = 's100';
~~~

Ý nghĩa:

- `USING TIMESTAMP` chỉ định **write timestamp theo đơn vị microsecond** cho mutation theo CQL.
- `USING TTL` chỉ định lifetime theo giây cho dữ liệu tương ứng.

Không nhầm hai loại tham số. Giá trị timestamp trong ví dụ là số minh họa, **không phải thời điểm bắt buộc của ngày hiện tại**. Chỉ dùng client-assigned write timestamps khi thiết kế hiểu rõ conflict semantics, allowed ranges và driver/server version.

## 44. Cassandra: timestamp quá xa trong tương lai

Một client có clock đi nhanh nhiều phút/giờ có thể tạo mutation với write timestamp ở tương lai.

Nếu hệ chọn timestamp lớn hơn khi reconciliation, một update sau đó nhưng timestamp bình thường có thể không thắng, tạo hiện tượng dữ liệu “không cập nhật được”.

Biện pháp:

- Đồng bộ clock và alert future skew.
- Không để client tùy ý gửi write timestamp khi không cần.
- Quan sát anomalous timestamps.
- Dùng CAS/LWT hoặc data model tránh last-timestamp quyết định nghiệp vụ quan trọng.
- Có runbook sửa dữ liệu có chứng minh source of truth, không tự ghi timestamp vô hạn lớn hơn.

## 45. Cassandra TTL và tombstone gắn với thời gian

TTL giúp một cell/row hết hiệu lực theo cơ chế database; dữ liệu hết hạn và deletion/tombstone có thể tham gia quy trình reconciliation, compaction và repair.

Cần quan sát:

- Node clock health.
- Time-to-live semantics theo engine/version.
- Tombstone accumulation.
- Repair schedule.
- Consistency level.
- `gc_grace_seconds`/deletion propagation theo thiết kế (không thay thế việc kiểm engine docs).
- Tác động khi node offline quá lâu rồi quay lại.

**Tăng TTL** không tự sửa đồng hồ lệch, và **giảm grace/deletion retention** bừa bãi có thể tạo nguy cơ dữ liệu cũ sống lại trong những failure scenarios thích hợp.

## 46. MongoDB wall-clock Date khác logical timestamp

Trong MongoDB:

- BSON `Date` biểu diễn thời điểm theo epoch milliseconds trong một trường dữ liệu.
- MongoDB có các logical timestamp/cluster-time metadata dùng cho replication/causal/session semantics theo capability.
- `operationTime`/`clusterTime` theo context không phải Java `Instant` do caller tự tạo.
- `ObjectId` có timestamp portion nhưng không tự là commit order.

Một query của ứng dụng nên phân biệt **audit wall timestamp** với **source version/cluster logical time** dùng cho ordering và consistency semantics.

## 47. MongoDB: server-set wall time vẫn cần contract

MongoDB có các update operators giúp đặt field theo server time theo API hỗ trợ, ví dụ ý tưởng:

~~~javascript
db.orders.updateOne(
  { _id: "order-100" },
  { $currentDate: { updatedAt: true } }
);
~~~

Lợi ích: tránh phụ thuộc trực tiếp vào clock của client cho `updatedAt`.

Giới hạn:

- Field vẫn dùng **wall clock** của server/đường thực thi.
- Failover và distributed ordering không tự được chứng minh.
- Nhiều writes cùng timestamp resolution.
- Không thay `version`/CAS cho update ordering.
- Không dùng `updatedAt` làm exclusive lock token.

## 48. MongoDB: TTL index không là lease expiry chính xác

Một TTL index có thể dùng để xóa documents đủ điều kiện hết hạn theo chính sách của database.

Nhưng:

- TTL deletion chạy bất đồng bộ theo engine mechanisms.
- Document hết hạn có thể **vẫn tồn tại** cho đến khi background cleanup.
- Hệ có thể chịu ảnh hưởng load/replica/TTL monitor schedule.
- TTL không tự chặn client dùng document expired.
- Deletion và visibility phải được hiểu theo deployment/read concern.

Nếu `session.expiresAt` dùng cho authorization, **ứng dụng/authoritative check phải từ chối khi đã hết hạn**, không đợi document thực sự biến mất.

## 49. DynamoDB: TTL là eventual cleanup

Amazon DynamoDB TTL sử dụng trường expiration time theo semantics của dịch vụ (epoch seconds với định dạng phù hợp), và expired items thường được xóa **bất đồng bộ**, không được hứa biến mất đúng giây hết hạn.

Ví dụ item:

~~~json
{
  "pk": "SESSION#s100",
  "tenantId": "t17",
  "expiresAt": 1794650400
}
~~~

Ứng dụng đọc item phải tự áp business expiration check nếu muốn từ chối session ngay khi quá hạn. TTL attribute không tự là conditional lease/lock authority hoặc authentication enforcement.

Không giả định DynamoDB có `serverNow()` để so clock hiện hành trong mọi ConditionExpression; nhiều thiết kế condition dùng giá trị thời gian **do client tính**, cần xử lý skew và authority riêng.

## 50. DynamoDB: conditional writes không dựa hoàn toàn vào timestamp

Cho một Inventory item:

~~~text
version=41
available=2
```

Hai clients đọc v41. Một conditional update yêu cầu `version=41`, giảm available và tăng version. Chỉ một writer thắng đối với cùng version theo atomicity API; writer còn lại cần re-read.

Đó là **ordering bằng state/version**, khác việc chọn “client timestamp nào lớn hơn”. Khi domain cần tránh overselling, conditional write phù hợp hơn `UPDATE if updatedAt < clientNow`.

## 51. Redis: TTL do server quản lý nhưng vẫn không là global lock

Redis có TTL/expiration, ví dụ:

~~~text
SET session:s100 value EX 600
TTL session:s100
PTTL session:s100
```

Expiration dựa trên Redis server time/implementation và được áp theo semantics của Redis. Những nguy cơ vẫn có:

- Key expired nhưng stale Java worker chưa biết.
- Redis failover/replication có một số rủi ro mất trạng thái lock tùy topology.
- Owner cũ có thể đang chạy operation dài.
- Application timeout/cancellation không đồng nghĩa DB write chưa xảy ra.
- TTL quá ngắn khiến hai workers chồng thời gian hoạt động.

Vì vậy **Redis TTL là một công cụ expiration**, còn distributed lease correctness cần protocol và downstream guards.

## 52. Redis EXPIRE không thay kiểm quyền nghiệp vụ

Nếu token/session có hạn:

~~~text
expiresAt = 10:00:00
Redis key expiration eventually removes session object
```

Một read ngay sát boundary phải theo chính sách: đã quá `expiresAt` thì từ chối, ngay cả khi Redis key còn tồn tại theo implementation hoặc dữ liệu đến từ cache khác.

Ngược lại nếu key bị Redis evict trước thời hạn do memory pressure, đây là cache/session storage availability issue, không tự chứng minh user đã bị revoke vì business expiry.

## 53. Timestamp metadata cần timezone và precision rõ

Một schema:

~~~json
{
  "createdAt": "2026-11-14T08:00:00.123Z",
  "sourceVersion": 42,
  "expiresAtEpochSeconds": 1794650400,
  "lastAppliedLogPosition": "shard-1/position-1002"
}
~~~

Bốn trường khác nhau:

- `createdAt`: wall time.
- `sourceVersion`: logical ordering per entity.
- `expiresAtEpochSeconds`: absolute expiry theo contract.
- `lastAppliedLogPosition`: replay checkpoint trong một log/shard.

Đừng dùng chúng thay nhau. Đặc biệt timestamp precision milliseconds vs microseconds vs seconds rất dễ gây bug **sớm/trễ 1.000 lần**.

## 54. 32-bit epoch và unit mismatch

Một lỗi:

~~~text
Java epoch milliseconds: 1794650000000
DynamoDB TTL expects epoch seconds: 1794650000
```

Dùng milliseconds cho field yêu cầu seconds có thể khiến TTL xa tương lai; dùng seconds tại nơi hiểu milliseconds có thể xem hết hạn từ lâu.

Nên:

- Đặt field names mang unit (`EpochSeconds`, `EpochMillis`).
- Dùng `Instant.getEpochSecond()` và `Instant.toEpochMilli()` có chủ đích.
- Validate numeric ranges.
- Test boundary, timezone và overflow.
- Không dựa vào format tự suy đoán.

## 55. Java: kiểu dữ liệu timestamp

~~~java
import java.time.Instant;
import java.time.Duration;

Instant createdAt = Instant.now();
Instant expiresAt = createdAt.plus(Duration.ofMinutes(15));

long ttlEpochSeconds = expiresAt.getEpochSecond();
long auditEpochMillis = createdAt.toEpochMilli();
~~~

Dùng `Clock` inject vào service thay `Instant.now()` trong logic cần test. Không dùng local timezone để tự tăng `expiresAt` khi ý nghĩa nghiệp vụ là *15 phút elapsed*, vì giờ mùa hè có thể ảnh hưởng các phép toán calendar-time khác.

---

## 56. Lease là gì?

**Lease** là một quyền sử dụng/chiếm tài nguyên **có thời hạn** do một authority hoặc giao thức xác định.

Ví dụ:

~~~text
Resource: partition-17
Lease holder: Worker A
Lease identifier: L-100
Term/fencing token: 72
Lease expiration: theo authority
```

Lease có thể phục vụ:

- Leader election cho một shard.
- Chạy scheduled job chỉ một owner.
- Điều phối compaction/snapshot.
- Phân công CDC partition.
- Phân phối queue consumers.
- Cấp quyền ghi trong một khoảng có điều kiện.

Khác mutex local Java, lease phải xét **nhiều máy, mất mạng, pause, failover và clocks không đồng nhất**.

## 57. Lease khác lock vĩnh viễn

Một lock không có expiration có thể bị giữ mãi nếu owner crash. Lease có expiry giúp **thu hồi khả năng tiến triển (liveness)**.

Nhưng giới hạn thời gian cũng tạo rủi ro:

~~~text
Worker A holds lease
Worker A pauses longer than TTL
Coordinator expires lease
Worker B acquires
Worker A resumes
```

Nếu không có kiểm tra quyền ở resource, A và B có thể cùng gửi writes.

Lease giúp recovery khỏi crashed owner; **nó không tự ngăn zombie owner**.

## 58. Ai là nguồn có thẩm quyền quyết định lease?

Có những mô hình khác nhau:

- Consensus-backed coordination store (ví dụ etcd/ZooKeeper theo API).
- Database conditional lease record với semantics và time authority đã thiết kế.
- Redis lock với TTL và các giới hạn failover/quorum của deployment.
- Leader/primary election nội bộ NoSQL.
- In-process timer chỉ cho local scheduling, không phải distributed lease.

Thiết kế phải xác định:

1. Ai cấp lease?
2. Ai tính/thông báo expiry?
3. Ai phát token/term tăng đơn điệu?
4. Khi authority mất quorum thì làm gì?
5. Resource đích kiểm owner ở đâu?
6. Lease renewal có thể race với revoke/failover không?
7. Khi caller không nhận response, outcome được reconcile thế nào?

Không để từng worker tự tuyên bố “tôi là leader vì `Instant.now()` chưa qua mốc”.

## 59. Lease expiry theo wall clock cần giả định mạnh

Nếu coordinator cấp expiry wall timestamp `E` và holder so với clock của chính nó:

~~~text
holder may be slow by 500 ms
coordinator clock may be fast by 500 ms
```

Holder có thể tiếp tục nghĩ lease còn hiệu lực **gần một giây sau** thời điểm coordinator cho là hết hạn, chưa tính network delay.

Nếu muốn chứng minh không overlap chỉ bằng thời gian, cần **bounded relative clock skew/uncertainty, drift, network/deadline và chính sách margin** được chứng minh. Khi những bound không còn đảm bảo, protocol phải fail closed hoặc chuyển sang fencing/authority checks thích hợp.

## 60. Ví dụ với uncertainty budget

Giả định không phải guarantee:

~~~text
Node A offset bound: ±60 ms
Node B offset bound: ±70 ms
Additional uncertainty budget: 30 ms
```

Một bound tương đối bảo thủ có thể là:

\[
\epsilon_{\text{pairwise}}
\le60+70+30=160\text{ ms}
\]

Một holder tự kiểm wall expiry `E` nên dừng **sớm hơn đủ safety margin** theo protocol thực, chứ không chờ tới đúng `now == E`. Tuy nhiên margin 160 ms **không tự là chứng minh** nếu không tính network delays, renew/ACK ambiguity, process pause hoặc source time failure.

**Safety margin là tham số của giao thức có giả định rõ, không là con số chọn theo trực giác.**

## 61. Monotonic lease clock và process pause

Một holder có thể tính local deadline khi lease được cấp:

~~~java
long leaseStarted = System.nanoTime();
long maxLeaseNanos = java.time.Duration.ofSeconds(10).toNanos();

boolean locallyExpired =
    System.nanoTime() - leaseStarted >= maxLeaseNanos;
~~~

Ưu điểm: hạn tự giới hạn không bị wall clock step (theo semantics monotonic clock).

Nhưng:

- Time spent awaiting grant/response phải được trừ phù hợp.
- Process có thể pause quá lâu rồi resume.
- Có thể có network requests đã gửi trước expiry nhưng commit sau.
- Restart làm mất local deadline.
- Các nodes không so `nanoTime` với nhau.
- Renewal có race với revoke/failover.

Không biến đoạn kiểm local deadline thành **distributed exclusivity guarantee**.

## 62. Tại sao lease duration không nên bắt đầu khi nhận response?

Ví dụ:

~~~text
t0 Coordinator issues lease for 10 seconds
t0+8s Network response finally reaches worker
t0+8s Worker starts its own 10-second timer
```

Worker có thể cho rằng mình còn hạn tới t0+18s, trong khi coordinator đã hết lease ở t0+10s.

Protocol cần tính **thời điểm request bắt đầu, thời gian roundtrip và thời hạn thực**, hoặc authority báo thời gian còn lại theo semantics được chứng minh. Không lấy một lease duration gắn vào response rồi khởi động trễ một full duration mà không trừ uncertainty.

## 63. Lease và GC pause

JVM có thể bị pause bởi:

- Stop-the-world GC.
- Safepoint/diagnostics.
- Process suspension.
- CPU starvation.
- Host virtualization pause.
- OS signal/debugger stop.

Trong khoảng pause, lease có thể hết hạn và owner khác được cấp quyền. Sau resume, code Java **không nên coi local Boolean `isLeader=true` là bất biến**.

Phải thiết kế **lease revalidation, fencing token hoặc authoritative conditional mutation** tại ranh giới thao tác quan trọng.

## 64. Lease và network partition

Sơ đồ:

~~~mermaid
flowchart TD
  A["Worker A holds lease term 7"] --> Split["Network partition"]
  Split --> Old["A cannot contact authority"]
  Split --> Quorum["Authority quorum remains reachable"]
  Quorum --> New["Worker B acquires term 8"]
  Old --> Sink["NoSQL target"]
  New --> Sink
~~~

Nếu A vẫn có đường tới một data sink nhưng không tới coordinator, việc mất heartbeat không tự ngăn A ghi. Đây là trường hợp **zombie holder** cần fencing tại sink, hoặc sink phải xác minh authority state theo protocol an toàn.

Một leader election service chỉ chọn B không đủ nếu dữ liệu đích chấp nhận A không điều kiện.

## 65. Fencing token là gì?

**Fencing token** là một số/term/revision **tăng đơn điệu theo quyền sở hữu** do authority phát.

~~~text
A acquires lease -> token 71
Lease expires
B acquires lease -> token 72
```

Resource đích có thể duy trì `maxAcceptedFencingToken` và **từ chối operations từ token cũ hơn** sau khi đã quan sát token mới.

Một token cần:

- Không bị tái sử dụng theo cùng resource/generation.
- Có ordering có nghĩa theo authority.
- Được dùng trong mọi mutation cần bảo vệ.
- Được kiểm atomically tại sink, không trong JVM rồi ghi vô điều kiện.
- Được xử lý với business version/idempotency để tránh lost updates.

Random UUID token phù hợp nhận diện owner nhưng **không tự có tính tăng đơn điệu** để fence old owner theo số thứ tự.

## 66. Một timeline fencing

~~~text
t0 A holds token=71
t1 A pauses
t2 Lease for A expires
t3 B receives token=72
t4 B writes target with token=72
t5 A resumes, writes with token=71
t6 Target rejects A (71 < maxAccepted=72)
```

Nếu sink kiểm token tại điểm commit, state không bị A **ghi ngược sau B** trong timeline này.

**Giới hạn quan trọng:** Nếu A viết ở t3.5 **trước khi sink nhận biết token=72**, chỉ lưu `maxAcceptedToken` ở sink có thể vẫn chấp nhận A. Để bảo đảm không có bất kỳ overlap sau expiry, sink phải có một giao thức authority/epoch gate hoặc thời gian lease được chứng minh, không chỉ đợi first write của B. Không quảng cáo fencing là phép màu giải quyết mọi race mà không định nghĩa linearization point.

## 67. Fencing và version CAS giải hai vấn đề khác nhau

- **Fencing token:** phân biệt quyền sở hữu cũ/mới của một worker/job/resource.
- **Business version:** chặn update từ state cũ hoặc lost update.
- **Idempotency key:** chặn thực thi trùng cùng business intent.
- **Lease expiration:** cho phép owner mới tiến triển khi owner cũ chết.
- **Consensus term/revision:** đặt một thứ tự của authority trong scope.

Một write có thể cần cả ba:

~~~text
if incomingFencingToken validForResource
and expectedBusinessVersion == currentVersion
and idempotencyKey not processed:
    apply mutation
```

Để đúng, những kiểm tra này cần nằm trong **atomic write/transaction boundary** phù hợp với nguồn có thẩm quyền. Việc kiểm trong application rồi gửi DB write sau đó vẫn có race.

## 68. Nếu chỉ kiểm token trong Java, vẫn có TOCTOU

Sai:

~~~text
Worker A reads authority: term=71, A valid
A pauses
Worker B acquires term=72
A resumes and writes NoSQL unconditionally
```

Đây là **time-of-check to time-of-use (TOCTOU)**.

Muốn an toàn cần:

- Kiểm điều kiện ngay tại storage mutation; hoặc
- Giao thức coordination/ownership chặn write ngay sau revoke; hoặc
- Fencing token với xử lý những race còn lại theo failure model; hoặc
- Thiết kế data owner/transaction protocol hỗ trợ mục tiêu.

Không coi `if (leaseValid()) repository.save()` là atomic.

## 69. `isLeader` flag trong memory chỉ là cache

Một flag:

~~~java
private volatile boolean isLeader;
~~~

có thể giúp bật/tắt job scheduling, nhưng:

- Không biết authority đã revoke khi mạng mất.
- Không bảo vệ pending async writes.
- Có thể còn true sau pause.
- Không so được với leader khác.
- Không thay term/revision/lease token.

Nên có một thành phần **lease manager** phát ra leadership state để kiểm soát scheduling, kết hợp **sink-side guard** cho dữ liệu quan trọng.

## 70. Redis `SET NX PX` để cấp lock có thời hạn

Ví dụ một lock key:

~~~text
SET lock:job:tenant17 random-owner-token NX PX 10000
```

- `NX` chỉ set nếu key chưa tồn tại.
- `PX 10000` đặt TTL theo milliseconds.
- Value là token unique để phân biệt owner khi unlock/renew.

Đây là một mẫu **expiring mutual-exclusion attempt**. Nó không tự có strong guarantees dưới mọi Redis failover/network partition, không cung cấp monotonically increasing fencing token và không ngăn một worker pause quá TTL rồi tiếp tục ghi.

Phù hợp hay không phụ thuộc **rủi ro side effect và giả định deployment**, không chỉ command trả `OK`.

## 71. Redis: unlock phải kiểm đúng owner

Sai:

~~~text
DEL lock:job:tenant17
```

vì A có thể xóa lock vừa được B tạo sau khi lock A đã hết TTL.

Lua script minh họa atomic compare-and-delete trên một Redis key:

~~~lua
if redis.call("GET", KEYS[1]) == ARGV[1] then
    return redis.call("DEL", KEYS[1])
end
return 0
~~~

`ARGV[1]` là random owner token đã lưu khi acquire. Script ngăn A xóa **lock của B** trong trường hợp value khác nhau, nhưng **không biến việc sở hữu lock thành quyền ghi vĩnh viễn vào một database bên ngoài Redis**.

## 72. Redis: renew lock cũng phải có điều kiện

Một heartbeat không nên dùng:

~~~text
PEXPIRE lock:job:tenant17 10000
```

mà không kiểm owner token; nó có thể gia hạn lock của một owner khác.

Một Lua script minh họa:

~~~lua
if redis.call("GET", KEYS[1]) == ARGV[1] then
    return redis.call("PEXPIRE", KEYS[1], ARGV[2])
end
return 0
~~~

Caller cần xử lý `0` là **đã mất ownership**, dừng công việc được bảo vệ và không giả định một request renewal timeout đã thành công. Để bảo vệ business write, vẫn phải có sink guard/coordination design phù hợp.

## 73. Redis replication/failover có thể tác động lock

Trong một số topology Redis với replication bất đồng bộ:

~~~text
A acquires lock on primary
Primary fails before replica sees write
Replica promoted
B acquires same lock on new primary
```

Hai clients có thể từng nhận tín hiệu sở hữu lock. Đây là một trong các lý do không coi **một Redis key trên asynchronous failover** là consensus-backed distributed lock cho những thao tác không được phép đồng thời.

Nếu dùng thuật toán đa node như Redlock, phải đọc kỹ **assumptions về clocks, network, failure modes** và yêu cầu correctness; không mặc định nó thay fencing/consensus.

## 74. etcd lease và leader election

**etcd** cung cấp các primitives như leases, key association, transactions và revisions với semantics dựa trên consensus trong phạm vi hệ hỗ trợ.

Một thiết kế có thể:

1. Tạo lease với TTL.
2. Gắn một key ownership vào lease.
3. Dùng transaction/compare để chỉ một contender thắng.
4. Theo dõi keepalive và lease loss.
5. Dùng một revision/term có thứ tự làm cơ sở fencing token theo protocol.
6. Kiểm quyền sở hữu tại sink hoặc đảm bảo gate phù hợp.

Không lấy `lease ID` ngẫu nhiên rồi coi nó tự tăng; **một integer revision hoặc sequence được authority đảm bảo** mới hữu ích cho fencing theo thứ tự.

## 75. etcd lease expiration vẫn không làm JVM đang chạy ngừng lại

Ngay cả khi etcd đã xóa key vì lease expired, worker cũ:

- Có thể chưa nhận watch event do network partition.
- Có thể đang pause.
- Có thể đang chạy long-running SQL/NoSQL operation.
- Có thể gửi buffered write sau khi hết lease.

Vì vậy etcd leader election là **nguồn phối hợp mạnh hơn nhiều cách làm ad hoc**, nhưng mọi side effect cần thiết vẫn phải xét **zombie worker/fencing và transaction boundary**.

## 76. ZooKeeper: ephemeral node và session

ZooKeeper sử dụng sessions và **ephemeral znodes** cho nhiều mẫu ownership/leader election.

Một session mất hiệu lực theo coordinator semantics có thể dẫn tới ephemeral znode biến mất, contender khác thắng. Tuy nhiên client cũ có thể chưa quan sát session expiration trong lúc mất mạng hoặc pause.

Tương tự:

- Session timeout không phải wall-clock `expiresAt` do các JVM tự so.
- Sequential znode ordering có thể phục vụ leader election theo recipe.
- Downstream state cần fencing hoặc version/epoch guard theo protocol.
- Không dùng path node ID ngẫu nhiên làm thứ tự tuyệt đối nếu không có guarantee.

## 77. MongoDB lease record: một cách dễ sai

Mô hình:

~~~json
{
  "_id": "job-100",
  "owner": "worker-A",
  "leaseUntil": "2026-11-14T08:10:00Z",
  "token": 71
}
~~~

Nếu hai clients tự dùng local `Instant.now()` để so và claim:

~~~text
if leaseUntil < myLocalNow:
    claim lease
```

đồng hồ sai lệch có thể làm claim sớm/muộn. Một cặp client check-then-update không atomically có thể claim cùng lúc.

Cần **atomic conditional mutation** và thiết kế *time authority/uncertainty*; đừng gọi một document có `expiresAt` là distributed lease an toàn chỉ vì update dùng MongoDB.

## 78. MongoDB: atomic CAS giữ owner/version nhưng chưa giải clock

Giả sử một `findOneAndUpdate` filter có:

~~~javascript
{
  _id: "job-100",
  ownerVersion: 71,
  leaseUntil: { $lte: clientNow }
}
~~~

và update owner/token. Filter+update có thể atomic trên một document, chặn **hai contenders cùng match một version** nếu filter đúng. Nhưng `clientNow` vẫn do client tạo; clock skew ảnh hưởng quyết định **đã thực sự hết lease hay chưa**.

Để có safety mạnh, cần authority timing contract, source-issued term/epoch và downstream guards, hoặc coordination service được thiết kế cho leadership.

## 79. DynamoDB conditional lease record có rủi ro tương tự

Một DynamoDB item với:

~~~json
{
  "pk": "LEASE#job-100",
  "owner": "worker-A",
  "expiresAt": 1794650100,
  "fencingToken": 71
}
~~~

có thể được claim bằng **conditional UpdateItem** để chỉ một contender thay đổi trạng thái theo điều kiện atomic.

Nhưng:

- `expiresAt` do client tính không tự là server-authoritative real time.
- DynamoDB TTL asynchronous deletion không chứng minh lease expired đúng thời điểm.
- Conditional writes bảo vệ state transition theo điều kiện được gửi, nhưng cần bounded skew/authority cho điều kiện thời gian.
- Strong consistency của một read không thay conditional write.
- Multi-region concurrent writers cần conflict policy riêng.

Không dùng DynamoDB TTL background delete làm cơ chế cấp lại quyền độc quyền có hard deadline.

## 80. Lease renew phải kiểm thế hệ owner

Một renewal an toàn hơn theo model:

~~~text
renew(resource, expectedOwnerToken, newExpiry):
    conditional update if
      currentOwnerToken == expectedOwnerToken
      and currentLeaseIsRenewableUnderAuthorityPolicy
    then update expiry
```

Nếu owner token không còn khớp, renewal bị từ chối. Nếu request timeout, không suy rằng renewal thành công; worker cần **reconcile status** hoặc dừng theo local safety deadline.

Không tự kéo dài lease bằng write không điều kiện vì có thể gia hạn quyền của owner cũ hoặc ghi đè B.

## 81. Một lease cấp cho hai node do clock skew: ví dụ

Giả sử:

~~~text
Coordinator's expiry time: real t=10.0s
Node A clock runs slow: t - 0.4s
Node B clock runs fast: t + 0.3s
```

Ở real t=9.8s:

- A đọc ~9.4s và cho rằng chưa expired.
- B đọc ~10.1s và có thể kết luận expired nếu tin clock riêng.

Nếu claim không có authority/atomic coordination, hai node có thể tự coi mình sở hữu lease.

Ngay cả có CAS để chọn một owner trong DB, A còn phải được **ngăn ghi tiếp** khi B đã được cấp. Vì vậy thiết kế đúng cần xử lý cả **acquisition** và **stale-holder execution**.

## 82. Lease loss cần fail-closed cho side effect quan trọng

Khi keepalive không thành công trong budget đã thiết kế:

- Ngừng nhận thêm jobs thuộc lease.
- Không tự retry external effect vô hạn.
- Hủy/đánh dấu cancellation cho công việc có thể dừng.
- Không phát ACK success cho việc chưa commit.
- Kiểm lại ownership/generation trước mutation quan trọng.
- Giữ idempotency cho tác vụ đã/đang commit.
- Coi writes in-flight có **unknown outcome** nếu response mất.

Không viết “nếu không kết nối được coordinator, cứ tiếp tục làm leader thêm 5 phút” trừ khi protocol thật sự có một safe extension bound rõ ràng.

## 83. Work đã bắt đầu trước expiry vẫn có thể commit sau expiry

Timeline:

~~~text
t0 A validates lease
t1 A sends remote write
t2 lease expires
t3 B becomes leader
t4 remote storage commits A's old write
```

Một kiểm tra tại t0 không tự ngăn commit tại t4. Để bảo vệ invariant, cần xác định **linearization point**:

- Storage kiểm term/epoch ngay trong commit?
- Một lease authority có tham gia commit?
- Có fencing token được cập nhật trước khi B xử lý?
- Có version CAS chặn stale business update?
- Có idempotent compensating workflow nếu side effect ngoài transaction?

“Check lease trước khi gửi” chỉ là một phần của safety case.

## 84. Term/epoch tăng đơn điệu cần bền qua restart

Nếu một authority restart và cấp lại `token=1` sau khi đã từng cấp `token=1000`, resource đích có thể không phân biệt owner cũ và mới.

Token/generation phải được tạo theo:

- Consensus revision/log index có semantics phù hợp.
- Durable database counter dưới transaction.
- Identity generation thay đổi sau rebuild.
- Phân vùng authority rõ ràng.

Không dùng `new AtomicLong(1)` trong mỗi worker rồi coi là globally unique monotonic fencing token.

## 85. Fencing tokens cần đúng scope

Ví dụ:

~~~text
Lease for partition-17: token=72
Lease for partition-18: token=45
```

Không so 72 và 45 như một thứ tự global nếu authority chỉ bảo đảm per-partition sequence. Token thường cần scope:

~~~text
(resourceId, generation, token)
```

Database mutation phải kiểm **đúng resource** để không có tenant/job này làm block tenant/job khác.

## 86. Fencing không thay idempotency của external API

Một worker A gửi `ChargeCard(operationId=K1)` trước khi lease mất, timeout, worker B sau đó gửi lại.

Ngay cả khi B có token mới, payment gateway có thể đã nhận request của A. Cần **business idempotency key** và outcome reconciliation với payment provider.

Fencing giúp hạn chế hành động từ owner cũ trong hệ có kiểm soát; nó không rollback được SMS/email/payment đã xảy ra.

## 87. Token mismatch không luôn là transient error

Nếu sink từ chối write vì `fencingToken=71` nhưng current=72:

~~~text
Outcome = STALE_OWNER
```

Worker không nên retry cùng token 71 100 lần. Hãy:

- Ngừng work.
- Bỏ leadership cache.
- Ghi metric stale-owner attempts.
- Điều phối lại job ownership.
- Không xác nhận work thành công.
- Kiểm unknown effects đã phát trước đó.

Đừng trộn fencing rejection với network timeout; chúng có cách xử lý khác nhau.

## 88. Một lease không đủ làm nguồn quyết định cho inventory

Giả sử một service “giữ lease” để bán món hàng cuối, nhưng cả hai services có thể commit theo những race khác nhau.

Thiết kế đúng hơn nên có **conditional write trên authoritative stock**:

~~~text
UPDATE Inventory
SET available = available - 1
WHERE available >= 1
```

với atomicity/transaction tương ứng. Lease có thể giúp giảm contention hoặc điều phối worker, nhưng **business invariant cuối cùng phải được bảo vệ ở điểm ghi dữ liệu có thẩm quyền**.

## 89. Leases cho background jobs khác leases cho business writes

| Trường hợp | Rủi ro khi hai workers overlap | Hướng bảo vệ |
|---|---|---|
| Rebuild cache | Lãng phí tài nguyên, có thể stale overwrite | Versioned refresh, idempotency |
| Compaction/reindex orchestration | Tải/consistency risk | Job generations + resource guards |
| CDC partition consumer | Duplicate events, checkpoint race | Per-partition ownership + idempotent sink |
| Notification sender | Gửi trùng | Stable notification ID, inbox/outbox |
| Payment job | Trừ tiền trùng | Provider idempotency key + state machine |
| Inventory reservation | Overselling | Atomic conditional source write |
| Leader of critical shard | Split-brain data corruption | Consensus term, sink fencing/commit gate |

Lease design phải theo **hậu quả overlap**, không theo một TTL mặc định dùng chung mọi job.

## 90. “Heartbeat đang chạy” không phải bằng chứng an toàn

Một worker có thể gửi heartbeats thành công nhưng bị kẹt:

- Job thread stuck trong I/O.
- Application event loop blocked.
- Background task queue dài.
- Network tới data sink lỗi.
- DB đã đổi term vì failover.

Heartbeat chỉ chứng minh một phần liveness theo đường đo, không chứng minh job đang đúng, không có old writes hoặc dữ liệu đang nhất quán.

Quan sát cả **lease keepalive state, actual progress watermark, checkpoint age, downstream errors và fencing rejections**.

---

## 91. Safety và liveness của một lease

Hai mục tiêu phải phân biệt:

- **Safety:** một điều bị cấm không xảy ra trong failure model đã nêu, ví dụ hai owners không cùng commit conflicting writes.
- **Liveness:** hệ có thể tiến triển, ví dụ khi A chết thì B được phép nhận công việc.

Lease TTL hỗ trợ **liveness**: khi worker biến mất, quyền không bị giữ mãi. Nhưng nếu thiếu fencing hoặc sink-side authority checks, B có thể bắt đầu trong lúc A vẫn chạy sau pause, làm mất **safety**.

Một thiết kế cần nói rõ *thời điểm B trở thành owner* và *điều kiện ngăn A tạo thêm tác động sau thời điểm đó*.

## 92. Không còn bound clock thì không còn lời hứa lease tương ứng

Giả sử protocol ghi:

~~~text
Maximum relative clock skew: 100 ms
Maximum uncertainty budget: 200 ms
Lease length: 10 seconds
~~~

Một node mất NTP nhiều giờ hoặc bị step 3 giây không thể tiếp tục dùng giả định skew 100 ms mà không đánh giá.

Với những thao tác cần độc quyền mạnh, hệ có thể phải:

1. Ngừng nhận thêm công việc theo lease.
2. Dừng/giới hạn những writes phụ thuộc lease.
3. Reconcile các writes có unknown outcome.
4. Khôi phục trusted time source.
5. Xác nhận authority term và fencing state.
6. Chỉ quay lại khi metrics/assumptions đáp ứng policy.

Không “tắt alert NTP” rồi mặc định hệ vẫn an toàn.

## 93. Cùng một NTP source sai có thể làm cả cụm cùng sai

Nhiều nodes có offset gần 0 so với **cùng một nguồn tham chiếu lỗi** chưa chắc thời gian UTC thực đúng.

Một safety assessment phải xét:

- Nguồn thời gian có đáng tin không?
- Có nguồn độc lập và source-selection hợp lệ không?
- Leap smear/leap-second policy có nhất quán không?
- Đường mạng có bất đối xứng lớn không?
- Nguồn có thể bị giả mạo/chỉnh clock không?
- Time server outage có làm node giữ bound cũ vô hạn không?

**Độ lệch nội bộ nhỏ** không chứng minh **thời gian tuyệt đối chính xác**, dù cả hai đều có ích cho những mục đích khác nhau.

## 94. Lag âm do trừ timestamp từ hai hosts

Giả sử:

~~~text
Producer wall clock = real time + 300 ms
Consumer wall clock = real time - 200 ms
Real transfer time = 50 ms
```

Nếu `publishedAt` từ producer và `receivedAt` từ consumer:

\[
\text{naiveLag}=50-300-200=-450\text{ ms}
\]

Một lag âm không phải consumer chạy ngược thời gian; đó có thể là **clock skew hoặc sai định nghĩa timestamp**.

Để quan sát pipeline, kết hợp **source commit/log position, consumer applied watermark, trace metadata và bound uncertainty**. Không dùng `abs(naiveLag)` để che tín hiệu cảnh báo.

## 95. Forensic timeline cần nhiều hơn wall timestamp

Sau sự cố:

~~~text
Node A logs leader-election 09:59:59.900
Node B logs data-write      09:59:59.850
Node C logs checkpoint      10:00:00.100
```

Thứ tự này có thể không phản ánh *happens-before* nếu clocks lệch. Điều tra cần:

- Consensus term, revision, epoch.
- Transaction IDs/commit log positions.
- Aggregate versions.
- Event IDs và idempotency keys.
- Trace/span IDs.
- Broker offsets trong cùng partition.
- NTP offset/uncertainty tại thời điểm incident.
- Network partition và node restart timeline.

Giữ nguyên raw audit records; có thể dựng **normalized timeline** riêng kèm phương pháp và uncertainty.

## 96. OS suspend và monotonic clock

Java `System.nanoTime()` có semantics của JVM/OS clock source. Trong những môi trường khác nhau, hành vi đo elapsed time qua **host suspend, virtual machine pause hoặc clock adjustments** có thể khác.

Nếu lease cần dừng sau 10 giây thực kể cả khi VM bị suspend, hãy xác minh behavior của runtime và authority protocol. Không tự cho rằng một timer local là bằng chứng không có thêm thời gian thực nào trôi qua.

Sau bất kỳ **long pause**, worker phải kiểm quyền sở hữu trước khi làm critical work.

## 97. Request deadline khác lease

**Deadline** giới hạn thời gian caller chờ kết quả. **Lease** là quyền được authority cấp để thao tác trên resource.

~~~text
HTTP deadline = 500 ms
Worker lease TTL = 10 seconds
DB write may commit after client timeout
```

Timeout HTTP không chứng minh write rollback. Lease expired không chứng minh remote transaction dừng. Cả hai đều cần **idempotent operation IDs và unknown-outcome reconciliation** nếu write có hậu quả nghiệp vụ.

## 98. Deadline propagation và retries

Một request qua Gateway → Java API → NoSQL driver có thể có nhiều timeout riêng.

Nếu Gateway chỉ cho 1 giây mà driver có retry budget 30 giây, Java có thể tiếp tục gửi attempts sau khi client đã hủy.

Một hướng:

- Đo elapsed/remaining duration bằng monotonic clock cục bộ.
- Gắn deadline budget vào requests theo contract.
- Bounded retry/backoff.
- Cancellation propagation ở mức hỗ trợ.
- Phân loại unknown commit.
- Durable async job khi công việc phải hoàn tất sau HTTP response.

Không dùng một `expiresAt` mơ hồ làm đồng thời HTTP timeout, TTL session và lease expiry.

## 99. JWT và certificate validity cũng phụ thuộc thời gian

JWT có các claims như `exp`, `nbf`; TLS certificates có `notBefore`, `notAfter`. Verifier clock lệch có thể từ chối token/certificate còn hợp lệ hoặc chấp nhận nó quá hạn.

Một thư viện có thể cho phép **clock leeway** cho JWT, nhưng leeway càng lớn thì cửa sổ chấp nhận quanh expiry càng rộng.

Cần time sync cho auth services, bound leeway theo policy và cơ chế revocation phù hợp. **Không tăng leeway hàng giờ chỉ để che host clock sai**.

## 100. Audit timestamp do client nhập không phải authority

Một API chấp nhận:

~~~json
{
  "action": "APPROVE",
  "approvedAt": "2099-01-01T00:00:00Z"
}
~~~

Nếu trường này quyết định approval order/lease validity, client có thể cố tình đưa giờ tương lai.

Phân biệt:

- **Client event-time** cho biểu mẫu/lịch sự kiện theo domain.
- **Authoritative recordedAt** do server/nguồn đặt.
- **Aggregate version** tăng theo atomic mutation.
- **Commit log position** do database/stream quản lý.

Không dùng user-controlled wall timestamp cho authorization hoặc exclusivity.

## 101. Cleanup job dựa vào đồng hồ cũng có thể gây hại

Một job xóa documents:

~~~text
DELETE WHERE expiry <= Instant.now()
```

Nếu host chạy nhanh một giờ, dữ liệu có thể bị xóa quá sớm.

Với destructive maintenance:

- Dùng trusted time/authority policy.
- Kèm business status/version điều kiện.
- Có soft-delete hoặc tombstone khi phù hợp.
- Audit/preview/dry run.
- Giới hạn tốc độ.
- Có backup/restore.
- Ngừng job khi clock uncertainty vượt bound.

TTL index/background cleanup và *business expiry* phải được hiểu riêng, kể cả khi cả hai cùng dùng field `expiresAt`.

## 102. Đồng hồ và key rotation/backup

Một backup có tên `backup-02-05` và một key rotation lúc `02:00 local` không đủ chứng minh backup dùng key version nào, nhất là khi clock/time zone không thống nhất.

Nên ghi:

- Immutable encryption key reference.
- Backup snapshot/log position.
- Rotation run ID/version.
- UTC timestamp với offset rõ.
- Restore metadata/manifest.
- Decrypt canary verification.

Tương tự, `createdAt` trên snapshot không tự là commit cut-off nếu backup engine dùng checkpoint riêng.

## 103. Nếu dùng timestamp-based LWW, hãy ghi rõ chính sách

Một số preferences có thể chấp nhận mất một concurrent update khi chọn timestamp lớn nhất. Nhưng quy tắc phải rõ:

- Thời gian của server hay client?
- Mức clock skew có thể chấp nhận?
- Tie-break cho timestamp bằng nhau?
- Có audit/conflict reconciliation không?
- Khi hai regions cùng viết, ai có authority?
- Rủi ro với users/tenants?
- Có thể sửa conflict thủ công?

**LWW là chính sách chọn winner**, không phải cơ chế chứng minh thứ tự commit thực.

---

## 104. Quan sát sức khỏe đồng hồ của từng node

Những signals hữu ích:

| Signal | Ý nghĩa | Cảnh giác |
|---|---|---|
| Sync state | Time daemon có synchronized không | `service running` chưa đủ |
| Selected source | Nguồn nào đang được tin | Nguồn có thể bị lỗi chung |
| Estimated offset | Sai khác ước lượng từ reference | Không tự là worst-case bound |
| Frequency/skew | Rate error và uncertainty | Phải hiểu unit/daemon |
| Root delay/dispersion | Error contribution từ upstream | Không bỏ qua |
| Holdover age | Bao lâu không có good sync | Drift tích lũy |
| Clock steps | Nhảy wall time gần đây | Có thể ảnh hưởng TTL/lease |
| Leap status | Time scale/event handling | Các sources có thể khác |
| Per-node max absolute offset | Outlier của cluster | Trung bình dễ che |
| Clock-dependent app failures | JWT/TLS/TTL/lease anomalies | Nguyên nhân có thể đa dạng |

Một dashboard ghi `lastOffset=2ms` nhưng không biết host đã mất sync vài giờ là chưa đủ để phục vụ protocol bounded skew.

## 105. Đo skew theo cluster, không chỉ average

~~~text
Node A:  +10 ms
Node B:  -15 ms
Node C: +2,000 ms
```

Average 665 ms không chỉ ra node C rõ bằng max absolute offset và per-node graph. Nếu các offsets có dấu ngược nhau, average còn có thể gần 0 trong khi pairwise skew lớn.

Đặc biệt theo dõi:

- Leaders/lease authorities.
- Database nodes nhận client timestamps.
- Kafka/CDC producers/consumers.
- Authorization/token verifiers.
- JVM hosts có critical scheduled jobs.
- DR/backup operators.

## 106. Prometheus: offset là metric quan sát

Nếu exporter cung cấp `node_timex_offset_seconds`, query ví dụ:

~~~promql
max by (cluster) (
  abs(node_timex_offset_seconds)
)
~~~

Tên metric/label và units phải kiểm theo exporter. Đây là **ước lượng offset** dùng cảnh báo, không phải phép chứng minh bound cho distributed lease.

Nếu node biến mất khỏi scrape hoặc metric không được xuất, cần alert **no-data** riêng, không coi mất metric là offset=0.

## 107. Prometheus: node không đồng bộ

Với một collector có gauge `node_timex_sync_status` theo semantics 0/1, một truy vấn minh họa:

~~~promql
count by (cluster) (
  node_timex_sync_status == 0
)
~~~

Đừng mặc định gauge này tồn tại hoặc 0 nghĩa failed trong mọi bản exporter. Xác minh metric contract và đồng thời monitor stale scrapes.

Đối với chrony, một số môi trường có exporter riêng cho `tracking`, `sources`, `dispersion` hoặc age từ lần sync.

## 108. Giám sát lease và ownership

Các tên metric khái niệm:

~~~text
lease_acquire_total{resourceClass,result}
lease_renew_total{resourceClass,result}
lease_renew_latency_seconds_bucket{le}
lease_ownership_lost_total{reason}
lease_local_safety_deadline_expired_total
lease_stale_token_rejected_total
lease_authority_unavailable_total
lease_work_aborted_total
lease_inflight_unknown_commit_total
lease_current_term{resourceClass}
```

Hãy tránh nhãn raw resource ID với cardinality rất cao. Dùng trace/log có kiểm soát để điều tra một key.

**Lease renew success** cũng không tự chứng minh worker xử lý job có tiến triển; cần progress/checkpoint watermark.

## 109. Đồng bộ các đồ thị trên một timeline

Một dashboard sự cố nên đặt cạnh nhau:

1. NTP/chrony sync status và offset theo node.
2. Source selection, step/slew events, holdover.
3. Coordination term, leader changes, lease renew failures.
4. JVM GC pause, thread starvation.
5. DB query/transaction p95/p99.
6. Fencing/CAS rejected writes.
7. Data/version anomalies (future timestamps).
8. CDC/replication lag và watermark.
9. Token/certificate validity failures.
10. Deploy, failover, VM migrations, admin changes.

Quan sát **thời điểm xuất hiện** không phải chứng minh nhân quả, nhưng giúp xác định giả thuyết đáng kiểm tra.

## 110. Ngưỡng cảnh báo phải gắn với safety bound

Ví dụ YAML vận hành minh họa:

~~~yaml
hostClock:
  requiredSync: true
  warningEstimatedOffsetMs: 50
  criticalEstimatedOffsetMs: 150
  maxHoldoverSeconds: 300
  onCritical:
    - withdrawCriticalLeaseHolders
    - investigateSourceAndClockSteps
~~~

Các con số **không phải default chuẩn**. Nếu lease protocol đòi maximum skew dưới 20 ms, ngưỡng 150 ms là quá chậm. Phải đặt alert dựa trên **uncertainty budget và safety case**, không chọn vì dashboard trông ổn.

## 111. Java: inject `Clock` để test business expiration

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;

public final class SessionPolicy {
    private final Clock clock;

    public SessionPolicy(Clock clock) {
        this.clock = clock;
    }

    public Instant expireAfter(Duration ttl) {
        return clock.instant().plus(ttl);
    }

    public boolean expired(Instant expiresAt) {
        return !clock.instant().isBefore(expiresAt);
    }
}
~~~

`Clock` hữu ích để kiểm expiry boundary, clock offset và timezone ở application level.

**Nó không là distributed time authority**: một `Clock.fixed`/`Clock.offset` trong Java unit test không thay clock của Redis/MongoDB/KMS.

## 112. Java: unit test expiry đúng tại boundary

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

Instant expires = Instant.parse("2026-11-14T09:00:00Z");

SessionPolicy p1 = new SessionPolicy(
    Clock.fixed(
        Instant.parse("2026-11-14T08:59:59.999Z"),
        ZoneOffset.UTC
    )
);

SessionPolicy p2 = new SessionPolicy(
    Clock.fixed(expires, ZoneOffset.UTC)
);

assert !p1.expired(expires);
assert p2.expired(expires);
~~~

Java `assert` chỉ hoạt động khi assertions được bật; dùng JUnit assertions trong bộ tests thực. Điều cần xác định là semantics `now >= expiresAt`, không dựa vào background TTL cleanup.

## 113. Java: mô phỏng hai hosts lệch clock

~~~java
import java.time.Clock;
import java.time.Duration;

Clock base = Clock.systemUTC();
Clock nodeFast = Clock.offset(base, Duration.ofSeconds(3));
Clock nodeSlow = Clock.offset(base, Duration.ofSeconds(-3));
~~~

Test các trường hợp:

- Session expired sớm/muộn.
- Source version so với client timestamp.
- Business approval order.
- Client-calculated TTL.
- Lease claim dùng local wall time.
- JWT leeway.

Test này **không chỉnh clocks của MongoDB/Redis/etcd server**. Muốn kiểm infrastructure behavior, cần integration/fault tests cô lập.

## 114. Java: giao diện lease authority minh họa

~~~java
import java.time.Duration;

public interface LeaseAuthority {
    LeaseGrant acquire(String resourceId, String workerId);

    RenewOutcome renew(
        String resourceId,
        long fencingToken,
        Duration requestedDuration);

    void release(String resourceId, long fencingToken);
}

public record LeaseGrant(
    String resourceId,
    long fencingToken,
    Duration grantedDuration) {}

public enum RenewOutcome {
    RENEWED,
    OWNERSHIP_LOST,
    AUTHORITY_UNAVAILABLE,
    UNKNOWN_RESULT
}
~~~

Các types là mẫu thiết kế, không phải implementation etcd/MongoDB/Redis. `UNKNOWN_RESULT` rất quan trọng: response timeout không được biến thành `RENEWED`.

## 115. Java: conservative deadline sau acquire

Một pattern local:

~~~java
long requestStartedNanos = System.nanoTime();

LeaseGrant grant = authority.acquire(resourceId, workerId);

long elapsed = System.nanoTime() - requestStartedNanos;
long ttlNanos = grant.grantedDuration().toNanos();
long marginNanos =
    java.time.Duration.ofMillis(500).toNanos();

long remainingNanos = ttlNanos - elapsed - marginNanos;

if (remainingNanos <= 0) {
    stopAndReconcile(grant);
} else {
    runOnlyWithinLocalDeadline(grant, remainingNanos);
}
~~~

Mốc bắt đầu **trước call** giúp trừ thời gian network response chậm. Tuy nhiên `500 ms` là giả định, không phải safe margin phổ quát. Đồng hồ rate error, process pause, lease grant time, authority semantics và sink-side writes vẫn phải được thiết kế chính xác.

## 116. Java: không dùng mutable leadership flag cho callback cũ

Một asynchronous callback có thể được tạo dưới token 71 nhưng chạy sau khi token=72 đã cấp.

Sai:

~~~text
onCallback():
  writeToDb(currentGlobalToken)
```

vì callback của job cũ có thể vô tình dùng token mới và vượt guard.

Hãy gắn **term/operation ID với work item lúc tạo**, propagate trong mọi retries; trước effect quan trọng cần sink CAS/fencing và xử lý stale-owner outcome. `volatile boolean isLeader` chỉ là cache trạng thái, không phải permission.

## 117. Java: `finally` không làm distributed lock an toàn

~~~java
try {
    performJob();
} finally {
    leaseAuthority.release(resourceId, token);
}
~~~

Nếu process crash, `finally` không chạy; lease TTL giúp liveness. Nhưng nếu release tới trễ sau khi B nhận quyền, **release phải check token**, không xóa quyền của B.

Quan trọng hơn, một remote write A đã gửi trước `finally` có thể commit sau khi lease mất. Cần protocol bảo vệ tại sink.

## 118. Retry vs stale-owner failure

Một `LeaseLostException`/`STALE_FENCING_TOKEN` không nên retry cùng token như lỗi mạng transient.

Phân loại:

| Outcome | Hành động điển hình |
|---|---|
| Authority/network timeout | Reconcile hoặc stop theo safe deadline |
| Renewed | Tiếp tục trong granted window |
| Ownership lost | Dừng critical work |
| Stale fencing token | Không retry token cũ |
| Business version conflict | Read current state, giải domain conflict |
| Unknown commit | Kiểm operation ID trước khi replay |
| Source throttling | Backoff có giới hạn |
| Invalid payload | Quarantine/repair, không retry vô hạn |

Không tự convert các outcomes này thành `false` rồi làm lại toàn bộ payment job.

## 119. GC pause và lease renewal

Worker A được lease 10 giây, GC pause 20 giây, worker B nhận lease mới. Sau GC:

- A không thể dựa vào Boolean `isLeader`.
- A cần ngừng work dưới old term.
- In-flight I/O có thể đã commit hoặc đang pending.
- Sink cần term/version guard.
- External operations cần idempotency.
- Metrics cần ghi long pause và stale-write attempts.

Đo `jvm_gc_pause_seconds` cùng renewal failures giúp điều tra, nhưng **correlation không là safety guarantee**.

## 120. Network partition giữa authority và sink

A không tới được etcd nhưng vẫn tới database. B có đường tới etcd quorum và nhận term mới.

Các câu hỏi:

- A có dừng theo local deadline không?
- Sink có biết B là owner theo giao thức chưa?
- A có pending writes có thể commit muộn không?
- Fencing `maxSeenToken` có khoảng trống trước first write của B không?
- Có business CAS chặn stale update không?
- Sau khi mạng hồi phục, state/checkpoint có được reconcile không?

Đây là tình huống khác với **kill A**, vì A vẫn có thể tiếp tục thực thi.

## 121. Khôi phục snapshot của coordination store

Giả sử authority trước đây cấp term 100, nhưng snapshot cũ chỉ có term 80. Nếu restore rồi cấp term 81, monotonic fencing bị phá.

Cần kế hoạch:

- Tái lập authority epoch/generation an toàn.
- Đồng bộ sink high-water marks.
- Chặn stale clients trước khi mở writes.
- Bảo vệ consensus membership/revision semantics.
- Verify không có term reuse.
- Test restore khi old workers chưa dừng hết.

Không coi backup coordination state giống backup một file cấu hình không có thứ tự.

## 122. Đồng bộ thời gian và data-loss recovery

Một replica bị offline lâu có clock lệch. Khi trở lại:

- Cassandra write timestamps/tombstones cần reconciliation theo engine.
- MongoDB replication logical order không nên bị so bằng wall time.
- TTL/cleanup có thể chạy bất thường.
- API user reads có thể gặp stale replica.
- Existing lease owner metadata có thể hết hiệu lực.
- Transaction/CDC checkpoints cần validate.

Trình tự rejoin nên dựa trên **database recovery protocol và time-health prerequisites**, không chỉ chờ TCP connection thành công.

## 123. Rủi ro khi đổi giờ production bằng tay

Một operator muốn ép `chronyc makestep` hoặc chỉnh OS time để xóa offset alert.

Trước khi làm phải cân nhắc:

1. Node đang giữ critical lease không?
2. Server có dùng client/server timestamps cho LWW?
3. Jobs cleanup có thể xóa nhầm không?
4. Certificate/token validity sẽ thay thế nào?
5. Có NTP source sai cần sửa trước không?
6. Có maintenance plan và rollback không?
7. Khi step xong cần rejoin/verify gì?

Không thực hiện clock step trên production node chỉ vì một metric đỏ mà chưa hiểu storage/coordination semantics.

## 124. Một runbook cho time-sync incident

~~~text
TRIGGER
  Clock drift or uncertainty exceeds the system's policy.

ASSESS
  1. Identify affected nodes, leaders, services and regions.
  2. Check time sources, last sync, offset and dispersion.
  3. Check steps, VM migration, OS/daemon changes.
  4. Determine whether lease safety bound remains valid.
  5. Inspect LWW future writes, TTL, auth/certificate failures.

CONTAIN
  6. Withdraw lease-sensitive workers if bound is broken.
  7. Stop destructive cleanup that needs trusted time.
  8. Preserve source versions/terms/operation IDs.
  9. Rate-limit retries and protect unknown commits.

RECOVER
 10. Restore trusted sync under OS/database playbook.
 11. Verify authority terms and sink fencing state.
 12. Reconcile business records affected by bad timestamps.
 13. Check replica/CDC catch-up and session validity.
 14. Rejoin nodes only after time-health and ownership checks.

CLOSE
 15. Confirm application SLO and business invariants.
 16. Record evidence and root cause.
 17. Improve alerting and fault-injection coverage.
~~~

Các hành động cluster step-down/sửa thời gian phải theo quy trình được phê duyệt. Mẫu này không phải command script tự chạy.

## 125. Runbook cho hai leaders

~~~text
TRIGGER
  Two workers report ownership or stale writes appear.

IMMEDIATE
  Identify resource, generation, term and authority state.
  Stop unsafe writes from uncertain owners.
  Preserve trace IDs, retries and in-flight operation IDs.
  Verify coordinator quorum and network partition.
  Verify sink-side term checks and stored max token.

RECOVER
  Establish one owner through authoritative protocol.
  Reconcile both owners' committed writes.
  Fix stale or duplicate external effects with idempotency.
  Restore checkpoints/projection consistency.
  Ensure no old worker can rejoin under reused term.

VERIFY
  Old term is rejected in critical write path.
  New term progresses.
  No business invariant violated.
  Monitoring and runbook documented.
~~~

Không xóa lock/lease records đại trà để “reset” nếu hệ có thể cấp quyền trùng trong recovery.

## 126. Khi nào nên dùng consensus thay vì custom TTL lock?

Hãy nghiêng về authority có consensus/revision khi:

- Hai leaders commit đồng thời sẽ làm sai dữ liệu nghiêm trọng.
- Cần strong ordering giữa owners.
- Có network partitions hoặc multi-region writes.
- Long pauses/retries phổ biến.
- Work có external side effects quan trọng.
- Recovery phải chứng minh safety sau failover.
- Không có một source DB operation đơn giản thay thế ownership.

Một Redis expiring key có thể đủ cho **best-effort cache rebuild** nếu trùng work chỉ gây lãng phí và output được version-guarded; không mặc định đủ cho double-charge prevention.

## 127. Không phải mọi job đều cần distributed lease

Có thể đơn giản hơn khi:

- Operation idempotent và duplicate không gây hậu quả.
- Queue phân phối job với at-least-once semantics và dedupe.
- Một nguồn đã có atomic condition để claim record.
- Mỗi shard có một owner cố định theo routing/partition assignment.
- Một task có thể chạy song song nhưng output được versioned.
- Scheduler chính có durable execution IDs.

Lease là một công cụ. Thêm distributed lease không đúng còn tăng KMS/NTP/authority dependencies và failure modes.

## 128. Khi có “unknown commit”, thời gian không trả lời được

Worker gửi write lúc 10:00:00, timeout lúc 10:00:01; lease hết lúc 10:00:02.

Không thể kết luận write đã commit trước lease expiration chỉ bằng các mốc thời gian này. Server có thể đã commit nhưng response mất, hoặc commit xảy ra muộn.

Dùng:

- Stable operation ID.
- Read/reconcile authoritative outcome.
- Transaction commit semantics.
- Idempotency marker.
- Fencing/business version guard.
- Outbox/ledger khi cần.

**Timeout là kết quả quan sát của client**, không phải bằng chứng abort của database.

## 129. Cross-region clocks không tạo global leader tự động

Hai regions có NTP/PTP và wall-time gần nhau nhưng mất kết nối. Cả hai có thể tiếp tục local writes.

Nếu domain cần một owner toàn cục:

- Single writer region theo authority.
- Consensus/quorum across configured failure domains.
- Fencing at authoritative sink.
- Explicit failover policy.
- No stale-owner side effects.
- Conflict reconciliation và audit nếu concurrent writes được phép.

NTP không tự tạo mạng, quorum hoặc atomic multi-region commit.

## 130. Một bảng chọn nguồn ordering

| Cần biết | Nguồn thích hợp | Không nên dùng thay |
|---|---|---|
| Request mất bao lâu | Monotonic elapsed | Wall time delta khi có step |
| User tạo record lúc nào | Server `Instant` | Transaction global order |
| State nào mới hơn trong aggregate | Source version | `createdAt` của client |
| Event tiếp theo trong một partition | Broker offset | Timestamp từ các partitions khác |
| CDC đã apply đến đâu | Source log/resume position | Thời gian local của consumer |
| Owner của resource | Authority term/lease | Local Boolean `isLeader` |
| Stale owner có được ghi? | Sink-side fencing/commit gate | “Tôi mới renew” |
| Token hết hạn chưa | Trusted wall expiry policy | Redis TTL cleanup |
| Có đúng một payment không | Business idempotency/ledger | Lease TTL duy nhất |
| Có thể report data age không | Source versions + time bounds | Raw timestamp subtraction |

## 131. Bộ lỗi thường gặp

1. Dùng `System.currentTimeMillis()` đo benchmark latency.
2. Lưu `System.nanoTime()` làm expiry dùng xuyên JVM/restart.
3. Đồng nhất UTC configuration với clock accuracy.
4. Coi last NTP offset là upper bound chắc chắn.
5. Quên pairwise skew có thể bằng tổng hai node errors.
6. Không tính drift trong giai đoạn mất đồng bộ.
7. Tùy tiện clock step khi service đang giữ leases.
8. Dùng `updatedAt` thay atomic version.
9. So Kafka offsets giữa partitions.
10. Coi ObjectId/ULID sort là commit order.
11. Dùng DynamoDB TTL xóa record như lock authority.
12. Dựa vào MongoDB TTL monitor để revoke quyền ngay lập tức.
13. Dùng Redis `DEL` lock không kiểm owner.
14. Không gia hạn Redis lock với owner token.
15. Dùng Redis asynchronous replication lock như consensus.
16. Giữ worker `isLeader=true` sau long GC pause.
17. Bắt đầu full lease TTL khi response đến trễ.
18. Gửi fencing token mới vào callback work cũ.
19. Bỏ business CAS vì đã có fencing token.
20. Retry stale-owner error như network timeout.
21. Tái sử dụng term sau authority restore.
22. Không kiểm sink khi authority cấp term mới.
23. Coi timeout chứng minh DB write rollback.
24. Không phân biệt lease loss với progress/heartbeat.
25. Bỏ TTL cleanup lag khỏi authorization tests.
26. Log time âm bị sửa bằng lấy trị tuyệt đối.
27. Chỉ đo cluster-average offset, che node xấu.
28. Tăng JWT leeway lớn để che broken time sync.
29. Không test network partition và zombie worker.
30. Coi lease TTL lớn hơn là giải pháp mọi race.

## 132. Đặc tả ứng dụng nên chọn fallback khác nhau

| Dữ liệu/tác vụ | Khi clock sync kém | Vì sao |
|---|---|---|
| Public catalog read | Có thể phục vụ theo policy freshness | Không cần exclusive write |
| Billing/ledger write | Fail closed/authoritative condition | Không được double-charge |
| Inventory reservation | Conditional source write | Clock skew không được phá invariant |
| Search reindex | Có thể postpone/retry | Duplicate work thường tốn tài nguyên |
| User session validation | Trusted expiry policy, có thể từ chối | Security time boundary |
| TTL cleanup | Pause destructive job nếu bound mất | Tránh xóa sớm |
| Lease-based leader | Withdraw/revalidate authority | Ngăn stale owner |
| CDC consumer | Tiếp tục theo offset/idempotency nếu protocol cho phép | Log order có thể độc lập wall time |
| Audit/event-time ingestion | Ghi uncertainty/provenance | Giữ lịch sử chính xác trong khả năng |

Không có một fallback chung cho mọi service. Safety và business requirement quyết định hành vi.

---

## 133. Bộ thí nghiệm an toàn cho clock/lease

Trước khi bật một thiết kế lease ở production, nên thử **trong môi trường cô lập** với những kịch bản sau:

| Tình huống | Inject điều gì? | Assert điều gì? |
|---|---|---|
| Clock fast | Worker A nhanh 2 giây | Không claim quyền sớm trái protocol |
| Clock slow | Worker A chậm 2 giây | Không tiếp tục critical write sau revoke |
| Wall step backward | Chỉnh wall clock lùi | Local duration không đo sai và owner bị revalidate |
| Wall step forward | Chỉnh clock tiến | Không xóa sớm dữ liệu/để job thiếu kiểm soát |
| Time-source outage | Ngắt trusted NTP trong test | Holdover bound được tính, fail-closed khi vượt |
| Long JVM pause | A pause > lease TTL | B tiến triển, A cũ không commit trái quyền |
| Lost renewal reply | Authority renew thành công nhưng response mất | A không tự giả định success |
| Unknown acquire | Response acquire mất | Không tự tạo second grant/owner trái protocol |
| Network partition | A không thấy authority nhưng thấy sink | A bị chặn tại điểm ghi |
| Coordinator failover | Authority restart/term đổi | Term không bị tái sử dụng |
| Sink snapshot rollback | Restore high-water token cũ | Không nhận lại stale owner |
| Redis failover | Primary lock chưa replicate | Không double-execute critical effect |
| TTL cleanup delayed | Expired item chưa bị xóa | Business expiry vẫn được thực thi |
| Timestamp in future | Cassandra client gửi timestamp cao | Future winner anomaly được phát hiện |
| Cross-host lag âm | Đặt clocks trái dấu | Telemetry không giả kết quả |

Không thao tác clock của **production host** để thử nghiệm. Hạ tầng time service, auth và database có thể cùng bị ảnh hưởng.

## 134. Viết assertion cho safety, không chỉ availability

Một fault test tốt có hai nhóm kết quả:

**Safety assertions**

- Không có hai conflicting commits được chấp nhận khi protocol cấm.
- Stale owner token bị từ chối theo authority term/commit gate.
- Không oversell inventory.
- Không double-charge cùng operation ID.
- Không resurrect document đã tombstone.
- Không chấp nhận session quá expiry policy.
- Không xóa dữ liệu quá sớm do clock fast.

**Liveness assertions**

- Sau khi A mất quyền, B có thể nhận work trong recovery budget.
- Khi authority quorum phục hồi, cluster có thể tiếp tục xử lý.
- Không deadlock/quarantine job mãi không điều kiện.
- Backlog/CDC tiến triển và được reconcile.
- Clients nhận outcome rõ hoặc có API tra cứu unknown operation.

Nếu test chỉ assert “B chạy thành công”, nó chưa chứng minh A đã bị chặn.

## 135. Một test harness cho zombie holder

Pseudocode:

~~~text
authority = FakeLeaseAuthority()
sink = SinkWithTermGate()

grantA = authority.acquire(resource="r1", holder="A")
pause("A")

advanceAuthorityClockBeyondAExpiry()
grantB = authority.acquire(resource="r1", holder="B")
sink.installAuthorizedTerm(grantB.term)
sink.apply(term=grantB.term, mutation="B update")

resume("A")
result = sink.apply(term=grantA.term, mutation="A old update")

assert result == STALE_OWNER
assert sink.value == "B update"
```

`installAuthorizedTerm` trong test đại diện cho **giao thức thực làm sink biết term mới**. Không được giả định hàm này tự tồn tại trong MongoDB/DynamoDB/Redis. Nếu production design chỉ nhớ token cao nhất khi có write, bắt buộc test trường hợp **A viết trước B** để phát hiện khoảng trống fencing.

## 136. Test renewal có response thất lạc

Hai trường hợp:

~~~text
Case 1:
  A sends renew.
  Authority commits renewal.
  Response is lost.

Case 2:
  A sends renew.
  Request never reaches authority.
  Client receives timeout.
```

Trong cả hai trường hợp, A chỉ biết **outcome unknown**, không thể suy từ timeout rằng lease chắc chắn đã gia hạn hay chưa.

Assert:

- Worker giữ conservative local deadline.
- Có đường reconcile owner/term.
- Hết window mà chưa xác minh thì dừng critical work.
- Không tự gửi duplicate external side effect.
- Không chuyển unknown thành `true`.

## 137. Chương trình kiểm thử time synchronization

Một deployment có thể kết hợp:

1. **Unit tests:** Java `Clock.fixed`/`Clock.offset`.
2. **Driver integration:** kiểm conflict/version/TTL trên NoSQL sandbox.
3. **Virtual clock/fault injection:** host test skew, step, holdover.
4. **Coordination test:** lease pause, loss, renew, network partition.
5. **Disaster recovery:** restore authority/sink state từ snapshots lệch nhau.
6. **Soak/load:** contention, GC pauses, retry storms, high clock offset.
7. **Security:** expired JWT, certificate time validity, untrusted timestamp.
8. **Observability:** metrics/alert kích hoạt đúng và runbook có thể dùng.

Bài test phải ghi **OS/JVM/driver/database version, topology, fault duration và assertions** để có thể tái lập.

## 138. Một ma trận lựa chọn thời gian theo NoSQL engine

| Tính năng | Cassandra | MongoDB | DynamoDB | Redis |
|---|---|---|---|---|
| Write timestamp | Có semantics reconciliation theo timestamp | Application Date khác logical cluster time | App timestamp attr nếu tự lưu | App value/clock, server expiration khác |
| TTL cleanup | Cell/row TTL và tombstone semantics | TTL index background cleanup | TTL asynchronous item deletion | Server-side key expiration |
| Atomic conditional update | LWT trong scope | Single-document atomic filter/update | ConditionExpression | Commands/Lua trong scope |
| Multi-record transaction | Giới hạn theo primitives/version | Multi-document tx khi hỗ trợ | TransactWriteItems theo limits | MULTI/EXEC trong Redis scope |
| Leader/lock | Không mặc định client clock là lease | Lease document cần protocol riêng | Conditional lease record cần clock assumptions | SET NX PX có limitations |
| Ordering metadata | Partition/consistency/timestamps | Oplog/clusterTime/resume token theo scope | Stream sequence/shards theo scope | Stream ID theo stream |
| Phụ thuộc đồng hồ | Timestamp LWW, TTL | Audit Date/TTL, không nhầm logical ordering | TTL app epoch seconds, conditional time | Key expiry/TTL, failover behavior |

Đây là **bản đồ khái niệm**, không phải danh sách đầy đủ capabilities. Phải xác minh API, transaction/consistency scope và phiên bản thật trước khi thiết kế production.

---

## 139. Bài tập A — Skew giữa hai nodes

Node A đi nhanh 80 ms, node B đi chậm 90 ms so với cùng UTC reference.

**Hỏi:** độ lệch tương đối bao nhiêu?

**Hướng giải:** \(80-(-90)=170\) ms. Hai offset mỗi node dưới 100 ms vẫn có thể tạo pairwise skew lớn hơn 100 ms.

## 140. Bài tập B — Bound khi cả hai host có sai số

Giả định mỗi host có sai số clock **được chứng minh** không quá ±60 ms.

**Hỏi:** bound về pairwise skew là bao nhiêu?

**Hướng giải:** tối đa \(60+60=120\) ms theo mô hình, chưa kể các sai số không nằm trong bound đã nêu.

## 141. Bài tập C — Tích lũy drift

Maximum drift giả định 50 ppm, host mất sync 10 phút.

**Hỏi:** sai số thêm tối đa xấp xỉ bao nhiêu?

**Hướng giải:**

\[
600\times50/10^6=0.03\text{ s}=30\text{ ms}
\]

## 142. Bài tập D — Holdover vượt tolerance

Last trustworthy bound 20 ms, drift 50 ppm và host mất sync 40 phút. Protocol chỉ cho phép uncertainty 100 ms.

**Hỏi:** còn hợp lệ không?

**Hướng giải:** phần drift tới 120 ms, tổng ước lượng 140 ms trước các sai số khác. Không được dùng protocol như thể bound 100 ms vẫn đúng.

## 143. Bài tập E — Clock UTC và múi giờ

Một sự kiện lưu `2026-11-14T08:00:00Z`.

**Hỏi:** hiển thị tại Asia/Ho_Chi_Minh lúc nào?

**Hướng giải:** 15:00 ngày 14/11/2026, offset +07:00. Thời điểm thực không đổi.

## 144. Bài tập F — Monotonic cross-process

A gửi `System.nanoTime()` của JVM mình sang B để dùng làm absolute lease expiration.

**Hỏi:** có đúng không?

**Hướng giải:** không. `nanoTime` là elapsed time source với arbitrary origin, không so trực tiếp giữa các JVM/hosts.

## 145. Bài tập G — Wall clock đo latency

Một GET mất 100 ms, giữa call host clock bị step lùi 1 giây.

**Hỏi:** dùng `currentTimeMillis()` trừ ra có thể ra gì?

**Hướng giải:** số âm/sai; dùng monotonic elapsed.

## 146. Bài tập H — Offset nhỏ nhưng mất sync

`chronyc tracking` báo last offset nhỏ, nhưng time source unreachable 2 giờ.

**Hỏi:** có đủ chứng minh clock vẫn trong bound không?

**Hướng giải:** không. Xem holdover age, drift bound, dispersion, reference trust và time since good sync.

## 147. Bài tập I — Time server sai đồng loạt

Mọi host sync tới cùng một NTP server sai 10 giây.

**Hỏi:** pairwise skew thấp có chứng minh UTC đúng?

**Hướng giải:** không. Nguồn có thể cùng sai; cần reference trust và independent checks.

## 148. Bài tập J — Lamport order

Lamport timestamp của a = 5, của b = 8.

**Hỏi:** có thể khẳng định a *happened-before* b?

**Hướng giải:** không. Quan hệ happens-before kéo theo giá trị nhỏ hơn, nhưng chiều ngược lại không đúng.

## 149. Bài tập K — HLC thay transaction?

Hai services ghi concurrent values và cả hai có HLC.

**Hỏi:** HLC có tự ngăn lost update?

**Hướng giải:** không. Cần CAS/transaction/conflict protocol phù hợp; HLC là ordering metadata chứ không tự là atomic commit.

## 150. Bài tập L — ObjectId lớn hơn

Một ObjectId của document A lớn hơn B.

**Hỏi:** A có chắc commit sau B không?

**Hướng giải:** không. ObjectId timestamp/identifier generation không đồng nghĩa commit order.

## 151. Bài tập M — LWW và clock đi nhanh

Node A đi nhanh 5 giây ghi status=PENDING; hai giây thực sau B ghi PAID bằng timestamp thấp.

**Hỏi:** LWW theo timestamp có thể giữ status gì?

**Hướng giải:** PENDING có thể thắng dù xảy ra trước về thời gian thực. Dùng domain version/atomic state transition.

## 152. Bài tập N — Future timestamp Cassandra

Một Cassandra client phát write timestamp xa tương lai.

**Hỏi:** hậu quả?

**Hướng giải:** các writes bình thường sau này có timestamp nhỏ hơn và có thể không thắng reconciliation; cần kiểm timestamp source và corrective repair theo engine semantics.

## 153. Bài tập O — MongoDB Date và clusterTime

Một ứng dụng dùng `createdAt` do client gán thay `clusterTime` để sắp write history.

**Hỏi:** có đủ không?

**Hướng giải:** không cho commit/causal ordering. Wall timestamp và logical cluster metadata có meanings/scope khác nhau.

## 154. Bài tập P — MongoDB TTL

Session hết hạn nhưng document còn tồn tại vì TTL monitor chưa xóa.

**Hỏi:** app có được tiếp tục authorize không?

**Hướng giải:** không nếu business policy quy định hết hạn rồi. Kiểm trusted expiry ở read/authorization path.

## 155. Bài tập Q — DynamoDB TTL milliseconds

Field TTL cần epoch seconds nhưng client gửi epoch milliseconds.

**Hỏi:** nguy cơ?

**Hướng giải:** expiration sai unit/range, có thể không được cleanup như dự kiến. Dùng `Instant.getEpochSecond()` và unit-specific schema.

## 156. Bài tập R — Redis expired key và leader

A giữ `SET NX PX` 10 giây, pause 20 giây; B nhận lock. A resume.

**Hỏi:** A còn quyền update business database không?

**Hướng giải:** không suy được từ flag/token cũ; phải có authority/fencing/sink guard theo protocol, và idempotency.

## 157. Bài tập S — Delayed Redis unlock

A gửi `DEL lock:key` sau khi B sở hữu key.

**Hỏi:** sai ở đâu?

**Hướng giải:** unlock vô điều kiện có thể xóa quyền B. Dùng compare-and-delete atomic với unique owner token.

## 158. Bài tập T — Delayed lease response

Authority cấp TTL 10 giây, response tới worker sau 8 giây; worker khởi động timer 10 giây từ lúc nhận.

**Hỏi:** vấn đề?

**Hướng giải:** worker có thể làm việc 8 giây quá authority expiry. Trừ elapsed/uncertainty theo safe lease protocol.

## 159. Bài tập U — Token fencing chưa được nhìn thấy

B nhận token 72 nhưng chưa ghi gì vào sink. A token 71 viết trước B; sink đang lưu maxToken 71.

**Hỏi:** sink kiểm `token >= maxSeen` có chắc chặn A?

**Hướng giải:** không. Cần authority/term gate hoặc lease correctness proof giải quyết khoảng trống trước first write của B.

## 160. Bài tập V — JVM pause

A có lease TTL 10 giây, JVM pause 20 giây; B được cấp quyền sau 10 giây.

**Hỏi:** chỉ đặt `volatile isLeader` đủ chưa?

**Hướng giải:** chưa. A có thể resume với flag cũ; cần stop/revalidate và sink-side fencing/conditional writes.

## 161. Bài tập W — Renew timeout

Worker gửi request renew nhưng không thấy response.

**Hỏi:** kết luận gì?

**Hướng giải:** outcome unknown, không phải success/failed chắc chắn. Reconcile hoặc dừng critical work trước local safety deadline.

## 162. Bài tập X — Fencing token reset sau restart

Authority trước đây cấp token 500, sau restart cấp token 1.

**Hỏi:** có hợp lệ để fence old holders không?

**Hướng giải:** không nếu cùng resource/generation. Cần durable monotonic term hoặc generation/epoch mới.

## 163. Bài tập Y — Split brain khi chỉ mất một đường mạng

A không tới được coordinator nhưng vẫn tới DB; B có quorum coordinator.

**Hỏi:** kill-A unit test có mô tả đủ tình huống?

**Hướng giải:** không. Phải test zombie A vẫn chạy và cố ghi sau B được cấp term.

## 164. Bài tập Z — Lease và payment

A đã gửi thanh toán nhưng không nhận acknowledgment; mất lease, B retry dưới term mới.

**Hỏi:** fencing chỉ ở MongoDB có ngăn double charge ở gateway không?

**Hướng giải:** không. Cần stable business payment idempotency key và outcome reconciliation với provider.

## 165. Bài tập AA — Expired token và clock chậm

JWT verifier clock chậm 3 phút.

**Hỏi:** nguy cơ?

**Hướng giải:** có thể chấp nhận token đã hết hạn theo thời gian thực; sync, clock leeway nhỏ theo policy và revocation controls.

## 166. Bài tập AB — Lịch chạy theo local time

Một scheduler chạy đúng 02:30 ở khu vực có DST.

**Hỏi:** có ngày nào 02:30 không tồn tại hoặc lặp?

**Hướng giải:** có thể có theo zone/rules. Cần xác định misfire/gap/overlap và job idempotency.

## 167. Bài tập AC — Commit timeout

Write gửi trước lease expiry nhưng client timeout; lease sau đó hết.

**Hỏi:** có chứng minh write chưa commit không?

**Hướng giải:** không. Tra operation ID/transaction outcome, không tự phát lại non-idempotent write.

## 168. Bài tập AD — Kafka offsets

Offset 100 ở partition 0 và offset 100 ở partition 1.

**Hỏi:** chúng có cùng global order không?

**Hướng giải:** không. Offset có scope partition, không là UTC timestamp hay source entity version.

## 169. Bài tập AE — Negative CDC lag

Producer clock nhanh 300 ms, consumer clock chậm 200 ms, chuyển message thật 50 ms.

**Hỏi:** lag tính trực tiếp bao nhiêu?

**Hướng giải:** -450 ms theo phép đo sai lệch; cần time uncertainty/source positions thay vì coi đây là negative processing.

## 170. Bài tập AF — More accurate PTP

Cluster có PTP đạt clock accuracy rất tốt.

**Hỏi:** có thể bỏ conditional update khi bán món hàng cuối?

**Hướng giải:** không. Clock precision không thay atomicity/coordination bảo vệ invariant.

## 171. Bài tập AG — Key reuse và generation

Resource ID P bị xóa ở generation 1 term 100; tạo lại ở generation 2 term 1.

**Hỏi:** so 100 và 1 như một sequence liên tục có đúng?

**Hướng giải:** không. Cần (generation,term) theo authority và identity lifecycle.

## 172. Bài tập AH — Restore fencing high-water

Sink được restore về maxToken 70, authority đang term 73.

**Hỏi:** có thể mở writers ngay không?

**Hướng giải:** không mặc định. Recovery phải đồng bộ epoch/high-water, chặn old workers và test term guard.

## 173. Bài tập AI — Retry stale token

Sink trả STALE_OWNER cho token 71, term hiện tại 72.

**Hỏi:** retry token 71 với backoff có ích không?

**Hướng giải:** không; token cũ không hợp lệ. Dừng leadership work, reconcile và không tự đổi term trên work cũ.

## 174. Bài tập AJ — Clock step và cleanup

Node clock tiến một giờ và worker cleanup xóa mọi record `expiresAt <= now`.

**Hỏi:** nguy cơ?

**Hướng giải:** xóa dữ liệu sớm. Nên ngừng destructive job khi clock untrusted, dùng authority/conditional guards và restore plan.

## 175. Bài tập AK — Leader election vs business version

Event A có lease term 8, aggregate version 40; event B term 9, aggregate version 39.

**Hỏi:** có bỏ B chỉ vì 39 nhỏ hơn 40 không?

**Hướng giải:** phải xét protocol: term và business version là các trục khác nhau. B có thể không hợp lệ về business CAS; A có thể stale owner. Cần rules riêng cho cả hai, không cộng hay so số tùy tiện.

## 176. Bài tập AL — `last_offset` và source trust

Các host báo offset 0 với cùng một time server đã bị cấu hình sai.

**Hỏi:** có đủ chứng minh timestamps đúng UTC?

**Hướng giải:** không; nguồn có thể sai chung. Cần trusted independent reference và source health.

## 177. Bài tập AM — NTP fix bằng cách “nhảy giờ”

Clock sản xuất lệch 2 phút. Operator muốn step ngay trên leader.

**Hỏi:** cần kiểm gì trước?

**Hướng giải:** lease/TTL/timestamp/authorization assumptions, time source validity, runbook và kế hoạch withdraw/rejoin; không tự chạy step bất chấp dữ liệu.

## 178. Bài tập AN — Tính safety budget

Node A có bound 60 ms, node B 70 ms, extra network/measurement margin 30 ms.

**Hỏi:** bound tương đối bảo thủ trong mô hình?

**Hướng giải:** \(60+70+30=160\) ms. Nhưng cần biết các giá trị thực sự là proven bounds; không tự gọi 160 ms là full lease safety proof.

---

## 179. Checklist dành cho người thiết kế và vận hành

**Đồng hồ và synchronization**

1. Có dùng UTC/offset rõ cho persisted timestamps không?
2. Có phân biệt wall time và monotonic elapsed trong Java không?
3. Có tránh so `nanoTime` giữa hosts không?
4. NTP/chrony/PTP sources có được phê duyệt không?
5. Time-source trust và leap handling có đồng nhất không?
6. Có monitor source reachability, offset và uncertainty không?
7. Có biết pairwise skew bound chứ không chỉ last offset không?
8. Có tính drift khi host holdover/mất sync không?
9. Có giám sát clock step/slew bất thường không?
10. Có alert nodes không đồng bộ, thiếu metrics và node outliers không?
11. Container/VM có được kiểm host time source không?
12. Time settings có được kiểm soát bằng config/permission không?
13. Khi bound mất, có fail-closed policy cho critical work không?
14. Có kiểm timezone/DST/epoch unit boundaries không?
15. Các lệnh chỉnh giờ production có runbook và approval không?

**NoSQL timestamps và TTL**

16. Có xác định clock tạo `createdAt`/`updatedAt` không?
17. Có tránh dùng client timestamp như commit order không?
18. Có aggregate source version để chặn lost updates không?
19. Các clients Cassandra có chính sách write timestamps rõ không?
20. Có monitor future timestamp và clock skew không?
21. Cassandra tombstone/TTL/repair có được xem trong vận hành không?
22. MongoDB ObjectId/Date/clusterTime có bị nhầm không?
23. MongoDB TTL index có bị coi là exact authorization deadline không?
24. DynamoDB TTL có dùng epoch seconds đúng không?
25. DynamoDB expired item presence có bị coi session active không?
26. Redis expiration có bị coi automatic business lock không?
27. Có phân biệt event-time, publish-time, processing-time không?
28. Có dùng source log position/offset đúng scope không?
29. Có tránh lấy Kafka offset giữa partitions làm global order không?
30. Có xử lý multi-region concurrent writes theo domain không?
31. Có đo cross-host latency kèm clock uncertainty không?
32. Có bảo vệ destructive cleanup khỏi clock fast không?

**Lease và ownership**

33. Có authoritative lease/leader protocol không?
34. Ai cấp lease và tính expiry đã rõ chưa?
35. Clock assumptions của lease có được ghi thành bound không?
36. Holder có dùng monotonic conservative local deadline không?
37. Có trừ grant roundtrip/response delays khỏi usable lease window không?
38. Renew unknown và renew rejected có được phân biệt không?
39. Có stop critical work khi lease loss/clock uncertainty không?
40. Có test GC pause dài hơn lease TTL không?
41. Có test network partition authority/sink không?
42. Fencing token có nguồn monotonic/durable không?
43. Có namespace token theo resource/generation không?
44. Sink có kiểm token/term atomically tại commit không?
45. Có xét race trước first write từ leader mới không?
46. Business version/CAS có đi cùng fencing khi cần không?
47. External effects có stable idempotency keys không?
48. Release/renew có owner-token conditional check không?
49. Có tránh dùng Redis unlock `DEL` vô điều kiện không?
50. Có xác minh Redis failover assumptions trước khi dùng lock không?
51. Có tránh dùng Java `isLeader` flag như authority không?
52. Có tránh reuse term khi authority restart/restore không?
53. Recovery của sink có giữ fencing high-water/epoch không?
54. Có biết failover behavior khi coordination quorum mất không?

**Quan sát, kiểm thử và phục hồi**

55. Có per-node clock/chrony dashboard cùng leader transitions không?
56. Có metric lease renew errors, lease loss và stale token rejects không?
57. Có đo actual task progress thay vì heartbeat success đơn thuần không?
58. Có correlation với JVM GC pauses và network delay không?
59. Có alert timestamp far-future và negative lag anomalies không?
60. Có audit timeline dựa cả versions/terms/trace IDs không?
61. Có test wall clock step forward/backward không?
62. Có test NTP source outage + holdover threshold không?
63. Có test TTL expired-but-present behavior không?
64. Có test old-owner writes sau new owner term không?
65. Có test unknown commit/renew response lost không?
66. Có test authority and sink snapshot rollback không?
67. Có runbook fail closed cho lease-sensitive writers không?
68. Có runbook data correction khi client future timestamp không?
69. Có plan xử lý expired JWT/TLS certificates do clock skew không?
70. Có acceptance criteria safety/liveness và kiểm thử độc lập không?

## 180. Hợp đồng đồng bộ thời gian và lease mẫu

~~~yaml
cluster: InventoryNoSqlProduction
timePolicy:
  persistence:
    timestampRepresentation: UTCInstant
    epochUnit: explicitByField
    timezoneForDisplay: perBusinessContext
  osClock:
    trustedSources: multipleApprovedSources
    leapHandling: documented
    sourceAuthentication: accordingToThreatModel
    offsetMonitored: true
    uncertaintyMonitored: true
    stepsAlerted: true
    maximumHoldover: derivedFromDriftBudget
    unsafeClockAction: withdrawLeaseSensitiveWriters
  java:
    localDuration: System.nanoTime
    persistedTime: java.time.Instant
    injectableWallClock: true
    neverCompareNanoTimeBetweenHosts: true
ordering:
  mutableAggregate:
    authority: sourceVersion
    mutationControl: atomicConditionalWrite
  audit:
    wallTime: serverRecorded
    traceIdAndCommitMetadata: included
  cdc:
    sourceLogPosition: tracked
    duplicateEvents: idempotent
    lateEvents: evaluatedPerPipeline
  noGlobalOrderingFromClientTimestamps: true
ttl:
  sessionExpiry: verifyAtRead
  cleanupMayBeAsynchronous: true
  dynamodbEpochUnits: seconds
  mongodbTtlIndexIsNotAuthority: true
  redisKeyExpiryIsNotBusinessLease: true
lease:
  resourceKey: tenantIdAndPartition
  coordinator: consensusAuthorityWhenStrictExclusivityNeeded
  monotonicLocalDeadline: conservative
  renewUnknownOutcome: stopOrReconcile
  clockBoundFailure: failClosedForCriticalWork
  term:
    source: durableMonotonicRevision
    scope: resourceAndGeneration
  sink:
    atomicFencingCheck: required
    businessVersionCas: whenNeeded
    newTermVisibilityGap: explicitlyAddressed
  sideEffects:
    stableIdempotencyKey: required
    unknownCommitReconciliation: required
observability:
  - nodeClockOffsetAndUncertainty
  - timeSourceHealth
  - clockSteps
  - leaseAcquisitionAndRenewal
  - staleOwnerRejections
  - gcPauses
  - timestampAnomalies
  - replicaAndCdcWatermarks
faultTests:
  - clockFastAndSlow
  - clockStepBackAndForward
  - timeSourceLoss
  - longJvmPause
  - renewalResponseLost
  - authorityNetworkPartition
  - sinkRejectsOldTerm
  - authoritySnapshotRestore
  - expiredTtlDocumentStillPresent
  - futureTimestampConflict
~~~

YAML này là **tài liệu thiết kế**, không phải cấu hình cho chrony, Java, Redis, Cassandra, MongoDB, DynamoDB hay etcd. Những bảo đảm cần được triển khai và kiểm chứng trên provider/engine/version thật.

## 181. Một runbook thay đổi clock hoặc lease production

~~~text
BEFORE
  Record current time sources, offset, uncertainty per node.
  Record current leaders, terms, lease holders and deadlines.
  Identify timestamp-LWW, TTL and cleanup-sensitive services.
  Verify backup, monitoring and data repair readiness.
  Choose maintenance window with quorum headroom.

CHANGE
  Apply OS/time-source settings according to host playbook.
  Avoid unplanned wall-clock steps.
  Withdraw/rejoin critical lease holders where appropriate.
  Keep term monotonic and sink fencing state consistent.
  Monitor p99, retries, lease renew failures and clock offset.

VERIFY
  Time-health threshold and trusted source policy pass.
  No stale holder can commit after authority transition.
  Authorization/TTL boundaries work.
  Replication/CDC and scheduled jobs progress normally.
  Unknown commits are reconciled.
  Audit result and rollback decision.
~~~

Không tự lăn thay đổi từng node nếu điều đó làm mất quorum của hệ điều phối. Thứ tự thao tác phải theo **cluster membership và failure tolerance** thực tế.

## 182. Kết luận

Trong **Database No SQL**, đồng bộ thời gian là điều kiện vận hành quan trọng nhưng không phải lời giải thay cho giao thức nhất quán.

- **Wall clock** phục vụ lịch, audit và thời điểm; có thể step/slew và cần hiểu timezone, unit, offset.
- **Monotonic clock** phù hợp đo duration và deadline trong Java, không dùng làm global persisted timestamp.
- **NTP/chrony/PTP** giảm sai lệch nhưng bound phải xét time-source trust, dispersion và drift trong holdover.
- **Logical/HLC/commit version** phục vụ ordering theo những semantics cụ thể; không coi client wall timestamp là consensus order.
- **TTL** thường là expiration/cleanup, không tự làm business authorization hoặc hard distributed lease.
- **Lease** giúp leader/job ownership có hạn, nhưng GC pause và network partition tạo zombie workers.
- **Fencing token, term, sink-side atomic checks, business CAS và idempotency** bổ trợ nhau; vẫn cần xử lý race trước khi sink nhận biết term mới.
- **Runbook và fault tests** phải chứng minh safety dưới time jumps, lost renew, coordinator failure và snapshot restore, không chỉ kiểm throughput khi hệ khỏe.

> **Đồng bộ giờ tốt làm hệ dễ quan sát và giảm sai lệch. Tính đúng đắn phân tán đến từ định nghĩa rõ thứ tự, quyền sở hữu, điều kiện commit và hành vi khi các giả định đồng hồ không còn đúng.**

Mỗi khi viết một trường timestamp hoặc cấp một lease, hãy hỏi: **ai tạo thời gian này, bound sai số được chứng minh ra sao, điều gì xảy ra khi node pause/mất mạng, và tại điểm ghi dữ liệu có thẩm quyền ai ngăn được owner cũ?** Đó là cơ sở để vận hành cụm NoSQL an toàn.
