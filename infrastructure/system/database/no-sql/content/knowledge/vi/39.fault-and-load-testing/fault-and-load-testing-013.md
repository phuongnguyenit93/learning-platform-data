# Lưu cấu hình, hạt giống ngẫu nhiên và lịch sử để tái hiện kết quả

Một hệ thống Java chạy kiểm thử tải trên cụm MongoDB ba node trong 45 phút. Sau 20 triệu thao tác đọc/ghi, công cụ báo một trường hợp hiếm: API đã xác nhận một bản ghi mới nhưng một luồng đọc lại nhận giá trị cũ. Kỹ sư bấm “Run again” nhưng không thấy lỗi. Đợt kiểm thử thứ nhất tạo dữ liệu ngẫu nhiên, dùng một số timeout tùy môi trường, chủ động gây failover, và chạy hàng trăm workers. Báo cáo chỉ lưu “test failed at 02:13”. Không có seed, cấu hình consistency, vị trí chèn lỗi hoặc lịch sử từng thao tác. Kết quả đáng chú ý nhưng rất khó phân tích, kiểm chứng hay tái hiện.

Đây là bài toán **khả năng tái hiện kết quả (reproducibility)** trong kiểm thử lỗi và tải của hệ NoSQL. Một kiểm thử có ngẫu nhiên, đồng thời và sự cố hạ tầng cần lưu lại không chỉ assertion cuối, mà cả **cách tạo workload, môi trường thực, thứ tự các sự kiện quan sát được và bằng chứng trạng thái database**.

Bài học thuộc chương **Kiểm thử lỗi và tải**, module **Database No SQL**. Ta sẽ thiết kế **run manifest, cấu hình phiên bản hóa, hạt giống bộ sinh giả ngẫu nhiên, lịch chèn lỗi, lịch sử invocation/response, kết quả readback và gói bằng chứng phục vụ replay**. Bài cũng phân biệt tái hiện chính xác với tái hiện tương đương về ngữ nghĩa và cách thử lại theo xác suất; vận dụng với Java, JUnit, MongoDB, Cassandra, DynamoDB, Redis và CouchDB.

> **Nguyên tắc:** Một seed giống nhau không bảo đảm cùng lịch interleaving, cùng replica nhận request hay cùng thời điểm failover. Tái hiện đáng tin phải kết hợp **đầu vào được kiểm soát, môi trường được nhận diện, lịch sử đủ chi tiết, điểm chèn lỗi xác định và cách kiểm bất biến**.

Các cấu hình và đoạn mã bên dưới là ví dụ học tập. Không dùng fault injection phá hoại trên production hoặc thu thập dữ liệu khách hàng thật mà không có quyền và quy trình riêng.

## 1. Ba mức tái hiện cần phân biệt

| Mức | Mục tiêu | Có thể bảo đảm thế nào? |
|---|---|---|
| **Deterministic input replay** | Tạo lại cùng lệnh, key, giá trị, thứ tự *dự kiến* và fault decisions | Lưu seed, thuật toán PRNG, config, worker mapping |
| **Semantic/causal replay** | Tạo lại điều kiện gây race và quan hệ nhân quả | Lưu history, barrier, failpoint, topology, kết quả |
| **Statistical reproduction** | Thấy lại lớp lỗi với tần suất đo được | Chạy nhiều seeds/schedules, thu xác suất và confidence |

“Replay 100% từng nanosecond” thường không khả thi trong cụm phân tán thực. Lập lịch hệ điều hành, network, thread pools, GC, disk, replication và cloud scheduling biến đổi. Vì vậy mục tiêu thực tế là **tái tạo dữ liệu đầu vào**, **ép các ranh giới lỗi quan trọng**, và **chứng minh hoặc bác bỏ một bất biến trên lịch sử quan sát được**.

## 2. Vì sao chỉ lưu log kết quả là không đủ?

Một dòng:

~~~text
FAIL: stale read observed at 02:13:45
~~~

không trả lời:
- Client nào đã ghi, client nào đọc?
- Write ACK với mức durability/consistency nào?
- Key thuộc shard/partition và replica nào?
- Đọc bắt đầu trước hay sau write hoàn thành?
- Có failover hay network partition trong khoảng đó?
- Dữ liệu test được tạo ra bằng PRNG nào?
- Lệnh read đã đọc từ primary, follower hay cache?
- Lỗi có phải do read model eventual consistency đúng thiết kế?
- Có timeout khiến trạng thái commit không chắc không?
- Bản ghi có bị TTL hoặc tác vụ nền xóa không?

Một báo cáo phù hợp cần **cấu hình, lịch sử thao tác, lịch chèn lỗi, oracle và metadata về môi trường**.

## 3. Gói bằng chứng của một lần chạy

~~~mermaid
flowchart TD
    RUN["Run ID"] --> CONF["Effective config + versions"]
    RUN --> SEED["Master seed + derived streams"]
    RUN --> DATA["Fixture/snapshot references + checksums"]
    RUN --> HIST["Operations: invoke / complete / unknown"]
    RUN --> FAULT["Fault decisions, trigger, actual outcomes"]
    RUN --> ENV["Topology, engine, driver, system state"]
    RUN --> METRICS["Latency, QPS, lag, errors, resources"]
    RUN --> ORACLE["Invariant checks + final state"]
    CONF --> PACK["Reproducibility package"]
    SEED --> PACK
    DATA --> PACK
    HIST --> PACK
    FAULT --> PACK
    ENV --> PACK
    METRICS --> PACK
    ORACLE --> PACK
~~~

Bản thân run ID cần duy nhất để các lần thử không ghi lẫn artifacts. Seed **có thể giống** để tái tạo input; run ID **nên khác** giữa hai lần chạy để tránh đụng dữ liệu cũ.

## 4. Một run manifest có thể đọc độc lập

~~~yaml
run:
  id: "nosql-fault-20261114-001"
  suite: "lost-reply-and-failover"
  owner: "database-test-team"
  startedAtUtc: "2026-11-14T09:00:00Z"
  status: "FAILED"
environment:
  isolation: "ephemeral-test-cluster"
  databaseEngine: "mongodb"
  engineVersion: "record-actual-version"
  driverVersion: "record-actual-java-driver"
  javaRuntime: "record-exact-vendor-and-build"
  topologyRevision: "cluster-spec-hash"
  configDigest: "sha256-of-effective-config"
  schemaRevision: "schema-git-commit"
  testCodeCommit: "test-suite-git-commit"
workload:
  model: "open-loop"
  workerCount: 32
  targetLogicalOpsPerSecond: 2000
  durationSeconds: 900
  operationMix: {read: 70, create: 10, update: 15, delete: 5}
  masterSeed: "0x4D595DF4D0F33173"
  randomAlgorithm: "documented-prng-and-implementation"
faults:
  scheduleReference: "fault-schedule.jsonl"
  failurePoints: ["AFTER_WRITE_ACK_BEFORE_REPLY", "REPLICA_RESTART"]
artifacts:
  inputFixtureDigest: "sha256-fixture-bundle"
  historyReference: "history.jsonl"
  oracleReference: "invariants.json"
  metricsReference: "metrics-summary.json"
  checksumManifest: "artifact-checksums.json"
~~~

Đây là **schema minh họa**, không phải file cấu hình của một công cụ cụ thể. Mỗi reference phải dẫn tới artifact thật, có quyền đọc và retention phù hợp. Không lưu password, raw token hoặc customer payload trong manifest.

## 5. Lưu cấu hình hiệu lực thay vì chỉ file cấu hình gốc

Một hệ có thể nạp:
~~~text
defaults.yaml
  -> staging.yaml
  -> environment variables
  -> command-line overrides
  -> runtime feature flags
  -> service-discovery config
~~~

Nếu chỉ lưu `defaults.yaml`, người chạy lại không biết **giá trị nào thực sự có hiệu lực**.

Nên xuất bản:
- Effective config sau khi resolve precedence.
- Nguồn gốc và thời điểm override các field quan trọng.
- Giá trị timeout, retry, durability, read/write concern.
- Flags, operation mix, concurrency, pacing.
- Reference tới secrets thay vì giá trị bí mật.
- Digest của artifact config và chương trình chạy.

Một cấu hình đã được ghi phải phản ánh **trạng thái lúc kiểm thử**, không bị một lần sửa file sau đó ghi đè.

## 6. Cấu hình NoSQL cần chụp riêng

| Nhóm | Trường cần lưu hoặc tham chiếu |
|---|---|
| Engine | Edition, server version, feature compatibility, storage engine |
| Replication | RF, replica set membership, voters, shards, regions, racks |
| Consistency | Read/write concern, consistency level, read preference, transaction options |
| Durability | Journal/WAL, persistence, acknowledgement policies |
| Network | TLS/mTLS, proxy behavior, timeout values, retry layers |
| Driver | SDK/driver version, pool sizes, retry settings, topology discovery |
| Data model | Schema/index revisions, shard/partition keys, TTL/retention |
| Workload | Distribution, key popularity, read/write mix, think time, rate model |
| Faults | Trigger, target, duration, profile, recovery policy |
| Environment | CPU/RAM/disk, region/AZ, container image, deployment digest |

Những trường này đặc biệt quan trọng khi kết quả phụ thuộc leader election, replica lag, read preferences hoặc khả năng chịu partition.

## 7. Version hóa cả mã kiểm thử

Cùng seed và config nhưng mã test mới có thể:
- Dùng thuật toán sinh key khác.
- Đổi thứ tự gọi PRNG.
- Thay timeout.
- Xử lý `UNKNOWN` thành `FAILED`.
- Bỏ một assertion.
- Thay schema serialization.
- Thêm retry ở gateway hoặc driver.

Ghi:
- Commit hash của test harness và application.
- Version/package digest của workload generator.
- Dependencies/lockfile.
- JDK vendor + build.
- Container image digests.
- Migration/index definitions.
- Version của tool kiểm history.

**Một nhãn `latest` không đủ để tái tạo một lần chạy cũ.** Artifact nên được khóa bằng version hoặc digest bất biến.

## 8. Cấu hình biến động trong lúc chạy

Một cụm có thể thay:
- Leader/primary.
- Số replica khỏe.
- Autoscaling target.
- Rate limit.
- Feature flag.
- Retry policy động.
- Storage capacity.
- Network routing.

Manifest đầu kỳ chưa kể hết câu chuyện. Cần ghi các **config-change events** và topology snapshots trong suốt lần chạy, có thời điểm và nguồn. Một config change trong lúc lỗi xảy ra có thể là tác nhân quyết định.

## 9. Hạt giống ngẫu nhiên là gì?

Một bộ sinh số **giả ngẫu nhiên** (PRNG) biến seed thành một chuỗi giá trị:

\[
r_0,r_1,r_2,\ldots=\operatorname{PRNG}(\text{seed},\text{algorithm})
\]

Nếu thuật toán và cách tiêu thụ các giá trị giữ nguyên, cùng seed có thể tạo cùng chuỗi.

Ứng dụng trong test:
- Chọn key và operation.
- Chọn độ lớn payload.
- Quyết định client nào có request tiếp theo.
- Chọn thời điểm tương đối để chèn lỗi.
- Chọn distribution skew/hot keys.
- Sinh dữ liệu synthetic.

**Seed không chứa bản thân lịch thực thi của network và database**. Phải ghi thêm thuật toán/phiên bản PRNG, phạm vi generator và mapping tới logical actors.

## 10. Một seed không đủ nếu thuật toán đổi

Ví dụ:

~~~text
Run A: seed=42, java.util.Random.
Run B: seed=42, SplittableRandom.
~~~

Không có lý do kỳ vọng hai luồng số bằng nhau. Ngay cùng thư viện, thay version hoặc cách gọi `nextInt`/`nextLong` cũng làm chuỗi tiêu thụ khác.

Do đó lưu:
- Seed dưới dạng không mơ hồ (số, hex và signedness).
- PRNG algorithm/implementation.
- Range/distribution method.
- Số luồng PRNG.
- Quy tắc derive seed con.
- Test code commit.

Muốn tái hiện tuyệt đối input sau khi generator đã thay đổi, nên lưu **danh sách operation đã sinh hoặc input trace** ngoài seed.

## 11. Dùng PRNG riêng cho mỗi logical worker

Sai về khả năng tái hiện:

~~~java
Random shared = new Random(masterSeed);
// 32 threads cùng tranh gọi shared.nextInt().
~~~

Dù PRNG có thread-safe, **thứ tự thread nào tiêu thụ giá trị nào** có thể thay đổi. Worker A lần này nhận số mà worker B lần trước đã nhận.

Tốt hơn:
- Derive seed theo `workerId` ổn định.
- Mỗi worker giữ generator riêng.
- Không chia generator mutable giữa threads.
- Chọn mapping worker → key range/operation stream được định nghĩa.
- Ghi worker count và mapping, vì đổi số workers có thể đổi workload.

Ví dụ:
~~~text
masterSeed = S
seed(worker_0) = derive(S, "workload", 0)
seed(worker_1) = derive(S, "workload", 1)
seed(worker_2) = derive(S, "workload", 2)
~~~

Hàm derive nên ổn định qua version và tách domain; không chỉ dùng hashCode không có contract rõ.

## 12. Tách ngẫu nhiên dữ liệu, lịch tải và lỗi

Nếu workload generator và fault injector dùng **cùng generator theo thứ tự gọi**, thêm một lần `nextInt` để chọn payload có thể thay đổi toàn bộ fault schedule.

Nên tách:
~~~text
seedData     = derive(masterSeed, "data")
seedWorkload = derive(masterSeed, "workload")
seedFaults   = derive(masterSeed, "faults")
seedJitter   = derive(masterSeed, "jitter")
~~~

Nhờ đó thay cách sinh payload ít ảnh hưởng lịch fault. Trong thử nghiệm phân tán, có thể tách sâu theo `workerId` và `faultClass`.

## 13. Java: tạo luồng số cho workers

Ví dụ:

~~~java
import java.util.SplittableRandom;

public final class WorkerRandom {
    private static final long SALT = 0x9E3779B97F4A7C15L;

    public static SplittableRandom forWorker(
            long masterSeed, int workerId) {
        long derived = mix64(masterSeed ^ SALT ^ workerId);
        return new SplittableRandom(derived);
    }

    private static long mix64(long z) {
        z = (z ^ (z >>> 30)) * 0xbf58476d1ce4e5b9L;
        z = (z ^ (z >>> 27)) * 0x94d049bb133111ebL;
        return z ^ (z >>> 31);
    }
}
~~~

Mã minh họa một thuật toán derive có phiên bản ngầm trong source code. Một lần chạy phải lưu **test code digest và JDK runtime**, không chỉ masterSeed. Cần dùng nguồn ngẫu nhiên mật mã riêng cho secrets/token thực; generator test không phải công cụ tạo khóa bảo mật.

## 14. Randomness không nên quyết định identity một cách mơ hồ

Giả sử hai lần chạy cùng seed tạo `order-101`, nhưng lần đầu chưa cleanup sạch. Lần hai có thể gặp duplicate và cho kết quả khác.

Nên tách:
- `runId`: duy nhất cho từng execution.
- `logicalOperationId`: xác định thứ tự ý định nghiệp vụ trong run.
- `businessRecordId`: có thể gồm test namespace và operation ID.
- `attemptId`: định danh mỗi transport retry.
- `seed`: để tái sinh choices.

Ví dụ:
~~~text
runId = run-20261114-002
operationId = run-20261114-002-worker3-op44
attemptId = run-20261114-002-worker3-op44-attempt2
~~~

Để so hai lần replay, hệ phân tích có thể map logical operation ID về `worker3-op44`, nhưng dữ liệu persist nên được cô lập theo run hoặc reset sạch.

## 15. Seed phải được lưu **trước** hoặc ngay khi bắt đầu chạy

Nếu bài test fail vì JVM crash, một logger chỉ in seed sau khi kết thúc sẽ mất thông tin quan trọng.

Nên:
1. Sinh hoặc nhận seed.
2. Persist run manifest.
3. Xác nhận manifest đã lưu.
4. Tạo dataset và fault schedule.
5. Bắt đầu workload.
6. Ghi history streaming và checkpoints.
7. Kết thúc/đóng evidence package kể cả khi fail.

Không cần seed luôn cố định. Có thể chọn một seed mới mỗi run để mở rộng coverage, nhưng **phải in/lưu seed được chọn** vào report ngay từ đầu.

## 16. Input generation phải là một contract có phiên bản

Chỉ lưu:
~~~yaml
seed: 42
readRatio: 0.8
~~~

chưa biết key được chọn theo uniform, Zipf-like, hotspot window hay tenant weighting.

Lưu thêm:
- Keyspace size và partitioning.
- Distribution type, parameters, generator version.
- Read/write operation weights.
- Value size, nesting, array lengths.
- TTL distribution.
- Per-worker pacing/think time.
- Duration, op count hoặc end condition.
- Retry generator behavior.
- Các edge cases có cố ý đưa vào.

Tải NoSQL bị ảnh hưởng mạnh bởi phân bố khóa; cùng QPS nhưng hot-key distribution khác có thể tạo p99 hoàn toàn khác.

## 17. Open-loop và closed-loop là hai workload khác nhau

**Open-loop:** phát command theo tốc độ dự kiến, tương đối độc lập với thời gian response.

**Closed-loop:** mỗi worker chờ operation hiện tại xong rồi mới tạo tiếp.

Một manifest phải ghi mô hình:
~~~yaml
load:
  model: "open-loop"
  arrivalProcess: "poisson"
  requestedLogicalOpsPerSecond: 3000
  maxInFlight: 800
  durationSeconds: 600
~~~

Trong closed-loop, khi server chậm thì tốc độ tạo tải có thể giảm, dễ che quá tải. Trong open-loop phải giới hạn hàng đợi/load generator để không biến chính generator thành bottleneck. Muốn tái hiện cả hai, cần ghi **offered vs completed throughput**.

## 18. Lịch tải lý thuyết và lịch thực tế

Bộ sinh có thể quyết định:
~~~text
op1 scheduled at t=10ms
op2 scheduled at t=12ms
op3 scheduled at t=14ms
~~~

Nhưng Java runtime thực tế gửi:
~~~text
op1 invoked at 10.5ms
op2 invoked at 20.2ms (GC pause)
op3 invoked at 20.4ms
~~~

Khi kiểm p99 và race, **thời điểm gửi thực tế** mới phản ánh workload đã đến server. Lưu cả:
- Scheduled offset.
- Actual invoke monotonic offset.
- Queueing delay trong generator.
- In-flight count.
- Completion offset.
- Deadline/timeout.
- Retry attempts.

Nếu chỉ replay scheduled plan, ta chưa chắc tái tạo actual schedule do GC/OS khác.

## 19. Fault schedule cần mô tả quyết định và thực thi

Một fault injector có thể chọn:
~~~text
At planned t=60s: kill follower node B for 20s.
At planned t=150s: drop replies for 3% writes.
~~~

Cần ghi **planned** và **observed**:
- Khi nào quyết định fault?
- Lệnh điều khiển được gửi lúc nào?
- Node nào nhận/áp dụng?
- Controller có xác nhận hiệu lực không?
- Recovery bắt đầu/kết thúc lúc nào?
- Hạ tầng có tự failover ngoài kế hoạch không?

Một entry `fault=network partition at 60s` không đủ nếu partition thực chỉ hình thành ở 65s hoặc chưa bao giờ hình thành.

## 20. Prefer fault trigger theo sự kiện thay vì sleep tùy ý

Thử lỗi commit:

~~~text
Tạo op-17.
Server xác nhận business write đã commit.
Test hook ngay sau commit chặn response.
Client nhận timeout.
~~~

Điểm trigger này ổn định hơn:
~~~text
sleep 100ms
kill random server
~~~

vì thời điểm 100 ms có thể nằm trước hay sau commit tùy tải. Nếu muốn tái hiện lỗi **sau commit nhưng trước response**, cần hook xác định milestone tương ứng; nếu chỉ mất network, outcome có thể vẫn UNKNOWN và phải ghi như vậy.

## 21. Fault plan và fault history là hai artifacts khác

**Plan**:
~~~json
{
  "faultId": "f-17",
  "type": "DROP_RESPONSE",
  "trigger": {"afterMilestone": "WRITE_DURABLE", "operationId": "op-17"},
  "maxApplications": 1
}
~~~

**History thực tế**:
~~~json
{
  "faultId": "f-17",
  "event": "FAULT_APPLIED",
  "operationId": "op-17",
  "actualTarget": "api-node-2",
  "milestone": "WRITE_DURABLE",
  "effective": true,
  "controllerSequence": 81
}
~~~

Nếu failpoint không được trigger, báo `NOT_TRIGGERED` thay vì âm thầm coi test đã bao phủ failure mode.

## 22. Một lịch sử thao tác tối thiểu cần gì?

Với mỗi **logical operation**, ghi:
- `runId`, `operationId`, `actorId`, `attemptId`.
- Loại thao tác: `read`, `create`, `update`, `delete`, `conditionalWrite`.
- Logical key/resource token theo policy.
- Inputs hoặc canonical digest/fixture reference.
- Invocation start time.
- Completion/failure/timeout/UNKNOWN time.
- Response value hoặc digest/typed result.
- Error class/code, retry reason.
- Source version/transaction reference nếu có.
- Target node/shard/region nếu quan sát đáng tin.
- Consistency/durability options.
- Correlation/trace IDs.

Cần thiết kế schema để phân biệt **một command có nhiều attempts** với **nhiều logical commands**.

## 23. Ghi invocation và completion riêng

Một JSON Lines history:

~~~json
{"seq":1,"type":"invoke","opId":"op-17","actor":"client-2","fn":"write","keyToken":"k7","value":2,"monoNs":100000}
{"seq":2,"type":"invoke","opId":"op-18","actor":"client-3","fn":"read","keyToken":"k7","monoNs":110000}
{"seq":3,"type":"complete","opId":"op-17","outcome":"ok","monoNs":120000}
{"seq":4,"type":"complete","opId":"op-18","outcome":"ok","result":1,"monoNs":130000}
~~~

Ví dụ cho thấy hai operations **chồng lấn**: read bắt đầu trước khi write hoàn thành, nên kết quả `1` có thể tương thích với một số consistency contracts. Không thể kết luận stale read chỉ bằng thứ tự completion.

JSONL thuận tiện cho append/stream và xử lý mất process giữa chừng; một invocation thiếu completion cần được giữ là **pending/unknown**, không tự điền failure.

## 24. Lịch sử với timeout và commit chưa rõ

~~~json
{"type":"invoke","opId":"op-21","attemptId":"a1","fn":"insert","keyToken":"k9","monoNs":2000}
{"type":"fail","opId":"op-21","attemptId":"a1","code":"CLIENT_TIMEOUT","outcome":"UNKNOWN","monoNs":5000}
{"type":"invoke","opId":"op-21","attemptId":"a2","fn":"insert","keyToken":"k9","monoNs":7000}
{"type":"complete","opId":"op-21","attemptId":"a2","outcome":"REPLAYED_COMMITTED","monoNs":9000}
~~~

Việc `a2` replay thành công không chứng minh ngay `a1` đã commit nếu server idempotency record chưa được kiểm. Một oracle riêng cần ghi:
- Operation record.
- Business effect count.
- Durability/read consistency của phép kiểm.
- Những side effects bên ngoài.

History của client diễn tả **điều quan sát được**, không tự khẳng định state server.

## 25. History cần bảo toàn nguyên nhân và thứ tự từng client

Tối thiểu:
- `client-1` thực hiện op A rồi op B có thứ tự theo program order.
- Một request được retry phải có liên kết `retryOf` hoặc cùng logicalOperationId.
- Events fault có liên kết tới operation hoặc target liên quan.
- Trạng thái invoke/complete không bị tách khỏi nhau sau aggregation.
- Không làm mất các requests chưa kết thúc khi test bị kill.

Nếu sau khi đọc write của chính mình, client gửi một read khác, quan hệ **happens-before** đó có thể quan trọng để kiểm session guarantees.

## 26. Wall clock và monotonic clock

**Wall clock** hữu ích để liên kết với log vận hành và sự kiện ngoài test, nhưng có thể nhảy khi NTP điều chỉnh hoặc máy lệch giờ.

**Monotonic clock** thích hợp đo durations và thứ tự trong cùng process.

Trong Java:
~~~java
long startNs = System.nanoTime();
performOperation();
long elapsedNs = System.nanoTime() - startNs;
~~~

Không dùng `System.currentTimeMillis()` để đo độ trễ chính xác khi clock có thể chỉnh. Nhưng **giá trị `nanoTime()` từ hai JVM khác nhau không được giả định cùng gốc thời gian**; cần sequence/correlation và cơ chế đồng bộ thời gian nếu tổng hợp cross-host.

## 27. Vì sao timestamp từ hai nodes không đủ chứng minh order?

~~~text
Node A clock = actual + 25ms.
Node B clock = actual - 20ms.
~~~

Hai events thực xảy ra theo một thứ tự nhưng log timestamp có thể đảo. Cần lưu:
- Host identity và wall timestamp.
- Monotonic offsets theo process.
- Clock sync/offset metrics.
- Client request/response intervals.
- Trusted sequence hoặc commit position theo engine.
- Trace/span correlation nếu hữu ích.

Không xếp toàn bộ database writes bằng timestamp từ nhiều nodes rồi gọi đó là **global total order**.

## 28. Lịch sử cần giữ concurrency, không ép thứ tự giả

Một test log dạng:
~~~text
1. W1 success
2. W2 success
3. R1 success
~~~

có thể là thứ tự **logger flush**, không phải thứ tự invocation. Nếu ba operations chồng lấn, kết quả có thể phụ thuộc interleaving.

Một history cho phân tích consistency cần biểu diễn intervals:
~~~text
W1: [invoke 10, complete 80]
W2: [invoke 20, complete 40]
R1: [invoke 50, complete 70]
~~~

Từ đó biết W2 complete trước R1 invoke, nhưng W1 chưa hoàn thành tại lúc R1 bắt đầu. Đây là thông tin không thể khôi phục nếu chỉ ghi thứ tự dòng hoàn tất.

## 29. Linearizability và điều kiện lịch sử

Trong một lịch sử hoàn chỉnh, nếu operation A **hoàn tất trước** B bắt đầu, một thứ tự tuyến tính hóa hợp lệ phải đặt A trước B. Với operations chồng lấn, checker có thể thử các thứ tự tương thích.

Ví dụ một register ban đầu là `0`:

~~~text
write(1): invoke t=10, complete t=20
read():   invoke t=30, complete t=40 -> 0
~~~

Nếu cả hai đều thành công và read/write cùng đối tượng theo contract linearizable, lịch sử này **không hợp lệ** vì read bắt đầu sau write đã hoàn thành nhưng trả giá trị cũ.

Nhưng nếu read đọc follower eventual theo contract chỉ eventual consistency, kết quả đó chưa chắc là bug. Vì vậy artifact phải ghi **mô hình nhất quán được kỳ vọng**, không chỉ history.

## 30. Những operations UNKNOWN trong history

Giả sử:
~~~text
write(1) invoke -> timeout, commit UNKNOWN
read() -> 1
~~~

Có thể write đã commit. Không nên tự coi write là failed và gắn nhãn hệ không tuyến tính hóa.

Một checker/analyst có thể xem các histories có incomplete operations theo policy được công bố; đôi khi phải đối soát với durable operation ledger hoặc giữ nhiều khả năng commit.

**Không “sửa” history bằng cách tự thêm completion success cho đẹp đồ thị.** Lưu bản gốc và các suy luận/reconstruction findings riêng, kèm provenance.

## 31. Một history tối thiểu chưa chắc đủ kiểm mọi bất biến

Ví dụ bank-like ledger hoặc inventory:
- Một lệnh reserve stock có thể đụng hai keys.
- Một giao dịch có thể gồm nhiều mutations.
- Một request thành công ở HTTP nhưng outbox chưa publish.
- Một cache read có thể eventual.

Cần mô hình đúng:
- Register, set, counter hoặc queue.
- Atomic transaction/group nếu có.
- Idempotency per operation.
- Business postcondition.
- Read visibility và replica role.
- Các events downstream/side effects.

Mỗi checker chỉ có ý nghĩa trong **phạm vi mô hình nó thực sự đánh giá**.

## 32. Kiểm bất biến ngoài lịch sử request/response

Ví dụ invariants:
~~~text
No duplicate order per logical checkout.
Inventory never negative after committed reservations.
Every acknowledged order has one durable operation record.
No deleted customer document reappears after final barrier.
No access across tenant boundaries.
No missing committed outbox event.
~~~

Để chứng minh, có thể cần:
- Durable readback từ authoritative store.
- Unique index/transaction checks.
- Replica catch-up/convergence theo policy.
- Consumer inbox/outbox state.
- Final aggregate counts/checksums.
- Audit và nguồn event độc lập.

**History cho biết client quan sát gì; oracle cho biết business state sau đó ra sao**. Phải giữ cả hai.

## 33. Lấy mẫu có thể làm hỏng kiểm tra tính đúng

Với SLO metrics, sampling request traces có thể đủ để ước lượng latency. Nhưng với kiểm **linearizability hoặc at-most-once effects**, bỏ mất một số writes có thể khiến checker kết luận sai.

Nên tách:
- Metrics được aggregate/sample theo phương pháp thống kê.
- Trace diagnostics có sampling.
- **Correctness history đầy đủ** trong phạm vi workload/keys được dùng cho checker.
- Nếu không lưu toàn bộ, xác định phạm vi kiểm bị giới hạn và không đưa ra kết luận mạnh hơn bằng chứng.

Có thể giảm quy mô workload kiểm correctness thay vì sample ngẫu nhiên lịch sử rồi tuyên bố “không có lỗi”.

## 34. Lưu lịch sử khi số lượng thao tác rất lớn

Với hàng triệu operations:
- JSONL có thể nén theo block.
- Chia theo worker/epoch và gắn sequence.
- Dùng binary schema có version nếu cần.
- Chuyển lớn sang object storage với integrity checks.
- Giữ metadata/index để truy hồi theo `opId`, keyToken, fault window.
- Ghi checksum/byte length cho mọi segment.
- Flush có giới hạn và đo `historyEventsDropped`.
- Có chiến lược khi disk full và collector down.

Nếu history writer mất dữ liệu trong lúc database bị lỗi, test report phải đánh dấu **INCOMPLETE**, không coi lịch sử một phần là đầy đủ.

## 35. Instrumentation cũng ảnh hưởng kết quả

Ghi mọi event đồng bộ xuống disk có thể:
- Tăng latency.
- Thay đổi thread scheduling.
- Che race condition.
- Làm GC và I/O tăng.
- Trở thành bottleneck trước database.

Nên:
- Dùng bounded async buffers phù hợp.
- Preallocate/split files khi cần.
- Không log full payload cho mọi op.
- Lưu compact structured events.
- Đo observer overhead.
- Theo dõi mất record/gaps.
- Có chế độ correctness nhỏ nhưng capture đầy đủ và performance lớn với metrics phù hợp.

**Quan sát hệ có thể thay đổi hành vi hệ**, vì vậy cần nêu mức instrumentation trong manifest.

## 36. Snapshot dữ liệu đầu vào là một phần seed

Nếu dùng seed `42` nhưng lần một chạy trên dataset một triệu sản phẩm, lần hai trên dataset hai triệu sản phẩm, kết quả không tương đương.

Lưu:
- Fixture generator version.
- Fixture seed.
- Schema/index/validator definitions.
- Keyspace size và data distribution.
- Snapshot/backup reference.
- Counts/checksums per collection/partition.
- TTL starting state.
- Tenant distribution.
- Encryption/permissions configuration.
- Các data mutations khởi tạo trước run.

Có thể dùng **synthetic fixtures** để bảo đảm tính riêng tư và dễ reset. Một snapshot nhất quán từ nguồn có thẩm quyền thích hợp hơn tập records export tùy ý giữa lúc đang ghi.

## 37. Tái hiện lỗi bắt đầu từ môi trường sạch

Một run reproducible cần:
1. Dựng một cluster test với topology xác định.
2. Restore fixture/snapshot hoặc generate deterministic input.
3. Kiểm schema/index/roles/TTL.
4. Reset queues, caches và CDC consumers trong phạm vi test.
5. Kiểm cluster đã ổn định trước khi bắt đầu.
6. Ghi manifest và seed.
7. Chạy workload + fault controller.
8. Đóng/sync histories.
9. Thực hiện readback/consistency oracle.
10. Cleanup và lưu retention-approved evidence.

Nếu chạy lại trên dữ liệu cũ của lần trước, một retry có thể gặp duplicate key hoặc expired TTL không do lỗi ban đầu. Phải ghi rõ **clean replay** hay **stateful continuation**.

## 38. Workload digest và fixture digest

Ví dụ:
~~~text
configSha256 = H(canonicalEffectiveConfig)
fixtureSha256 = H(canonicalFixtureManifest)
workloadSha256 = H(canonicalLogicalOperations)
faultPlanSha256 = H(canonicalFaultPlan)
historySha256 = H(historySegments)
~~~

Digest giúp phát hiện artifact bị thay đổi ngoài ý muốn và biết hai lần chạy có cùng input hay không. Nhưng:
- Digest không chứng minh correctness.
- Hash của toàn bộ object không tự làm nó ẩn danh.
- Canonicalization cần ổn định.
- Một attacker có quyền thay tất cả artifacts có thể tính lại hashes; có thể cần signed manifest/immutable storage theo threat model.

Không ghi raw secret vào một gói test “được băm” rồi mặc định nó an toàn khi phát tán.

## 39. Java: ghi seed và effective config sớm

Ví dụ khung:

~~~java
record RunSettings(
    String runId,
    long masterSeed,
    int workerCount,
    int durationSeconds,
    String workloadModel,
    String testCodeRevision
) {}

void startTest(RunSettings settings, ArtifactWriter artifacts) {
    artifacts.persistManifestDurably(settings);

    for (int workerId = 0; workerId < settings.workerCount(); workerId++) {
        // Mỗi worker sẽ được gán PRNG theo ID ổn định.
        launchWorker(workerId,
            WorkerRandom.forWorker(settings.masterSeed(), workerId));
    }
}
~~~

`ArtifactWriter` và `launchWorker` là abstractions minh họa. Trong triển khai thật, phải xác minh manifest đã persist trước khi gửi workload, và ghi dữ liệu môi trường/driver config có hiệu lực sau khi kết nối được database.

## 40. Java: event recorder cho history

~~~java
record OperationEvent(
    String runId,
    String operationId,
    String attemptId,
    String clientId,
    String phase,
    String operation,
    String keyToken,
    long monoNanos,
    String outcome
) {}

void invoke(
    HistorySink sink,
    String runId,
    String opId,
    String attemptId,
    String keyToken
) {
    sink.append(new OperationEvent(
        runId, opId, attemptId, "client-1",
        "INVOKE", "READ", keyToken,
        System.nanoTime(), "PENDING"
    ));
}
~~~

Lược đồ cần mở rộng với input/result representation, concurrency/version/consistency context khi thực sự kiểm linearizability. `System.nanoTime()` chỉ so sánh trong cùng process; với nhiều clients, không tự ghép timestamps thành một global clock.

## 41. Một lịch sử “failed” không được sửa sau khi đọc oracle

Ví dụ:
~~~text
History gốc: Client timeout.
Oracle sau đó: Business row tồn tại.
~~~

Nên lưu:
~~~json
{
  "logicalOperationId": "op-17",
  "clientOutcome": "TIMEOUT",
  "serverOutcomeAtResponseTime": "UNKNOWN",
  "laterReconciliation": {
    "observed": "RECORD_EXISTS",
    "readConsistency": "authoritative-read",
    "observedAt": "later-time"
  }
}
~~~

Không thay `clientOutcome` thành `SUCCESS` vì điều đó xóa chứng cứ timeout đã xảy ra. Một trường hợp lỗi cần tái hiện có thể **phụ thuộc chính vào sự mơ hồ của phản hồi**.

## 42. JUnit: hiện seed và đường replay trong failure

~~~java
@Test
void randomCommandsPreserveInvariant() {
    long seed = Long.getLong("test.seed", 42L);
    System.out.println("REPLAY_SEED=" + seed);

    SplittableRandom random = new SplittableRandom(seed);
    TestModel model = new TestModel();

    for (int i = 0; i < 1000; i++) {
        int operationType = random.nextInt(3);
        model.applySyntheticOperation(operationType);
        assertTrue(model.invariantHolds(),
            "seed=" + seed + ", step=" + i);
    }
}
~~~

Đây là unit-model example. `TestModel` là lớp giả định, không phải code có thể chạy nguyên vẹn khi chưa định nghĩa. Một test integration còn phải ghi **config, fixture, fault plan và operation history**, không chỉ seed trong `System.out`.

## 43. Property-based testing và shrinking

Thay vì chỉ chạy seed cố định:
- Tạo nhiều seeds.
- Sinh chuỗi operations trong giới hạn.
- Kiểm invariants sau từng bước hoặc sau convergence.
- Khi thấy lỗi, lưu seed và toàn bộ input/history.
- Thu nhỏ chuỗi gây lỗi (**shrinking**) để tìm ít operations/clients/faults nhất.
- Chạy lại bản thu nhỏ với hook/barrier chính xác.

Ví dụ:
~~~text
Bản gốc: 20.000 operations, 16 workers, 3 network faults.
Bản tối giản: 2 writes cùng key + 1 response drop.
~~~

Một bản tối giản có thể giúp thấy race, nhưng nó **không mặc nhiên tương đương** bản gốc nếu lịch thực thi và database state thay đổi. Cần ghi cả lịch sử gốc và phép biến đổi thu nhỏ.

## 44. Lịch fault cần gần với quan hệ nhân quả

Một failpoint theo thời gian:
~~~text
At t=120s, disconnect primary.
~~~

Có thể không tái hiện nếu write cần kiểm đã hoàn tất trước t=120s.

Một failpoint theo sự kiện:
~~~text
When operation op-44 reaches AFTER_COMMIT_BEFORE_RESPONSE:
  drop its response exactly once.
~~~

Khả năng tái hiện cao hơn vì nó khóa vào milestone. Có thể phối hợp:
- Clock-relative faults cho stress.
- Event-triggered faults cho root-cause reproduction.
- Barriers giữa clients để tạo concurrency window.
- Confirmed fault-applied records.
- Auto recovery/cleanup.

Không dùng hook trong production mà không có scope và phê duyệt riêng.

## 45. Kịch bản lịch sử với hai writes cạnh tranh

Giả sử key `balance` bắt đầu `100`:

~~~text
Client A: read 100
Client B: read 100
Client A: write 90
Client B: write 80
Final: 80
~~~

Nếu nghiệp vụ kỳ vọng hai phép trừ 10 và 20, kết quả đúng có thể là `70`; đây là ví dụ **lost update**.

Để tái hiện:
1. Khởi tạo fixture balance=100.
2. Dùng barrier buộc A và B đều đọc trước khi ghi.
3. Cho A ghi rồi B ghi, hoặc hoán đổi có kiểm soát.
4. Ghi expected revision/conditional write.
5. Kiểm final state cùng audit/operation effects.
6. Nếu dùng CAS, một update phải conflict và được retry trên state mới theo business rule.

Chỉ seed chọn “A và B là hai writers” không quyết định được họ có đọc cùng state hay không. **Barrier mới điều khiển quan hệ cạnh tranh cần thiết**.

## 46. Tái hiện lỗi timeout sau commit

~~~text
1. Test tạo operationId ổn định.
2. Server nhận command.
3. Database commit theo write concern đã định.
4. Hook xác nhận commit milestone.
5. Proxy chặn response đi về.
6. Client ghi TIMEOUT/UNKNOWN.
7. Retry cùng operationId.
8. Oracle kiểm chỉ một business effect.
~~~

Gói bằng chứng phải có:
- Stable IDs.
- Fault applied event ở bước 5.
- Commit/result evidence ở bước 4.
- Request/response history theo attempts.
- Readback và side-effect counts.
- Durability/consistency config.
- Lệnh replay và prerequisites.

Không suy thành công chỉ vì retry trả `200`; cần kiểm **order count, inventory, payment, outbox** nếu workflow có những hiệu ứng đó.

## 47. Reproducibility trong failover

Khi kiểm primary/follower failover cần chụp:
- Replica/voter topology trước lỗi.
- Target node được dừng/restart và thời gian hiệu lực.
- Lag và source commit position.
- Election/leader-change events.
- Acknowledgement mode của writes.
- Các write outcomes UNKNOWN.
- Client reconnect/server selection.
- Trạng thái sau recovery.

Nếu một lần chạy có follower lag lớn và lần chạy sau mọi replica bắt kịp, kết quả khác có thể là **khác tiền điều kiện**, không phải lỗi ngẫu nhiên của tester.

## 48. MongoDB: lưu gì để tái hiện?

Ngoài các artifacts chung:
- MongoDB server, driver versions, topology replica set/sharded cluster.
- Read concern, write concern, read preference, retryable writes/transactions config.
- Collection validators và index definitions.
- Shard key/placement nếu có.
- Oplog/change stream retention, resume token dưới dạng opaque.
- Primary step-down/failover timeline, replication lag.
- Transaction labels/operation IDs, response errors.
- Query shapes và read/write results đủ cho checker.

Không log raw credentials hay full document PII vào history. Nếu dữ liệu cần đối chiếu, dùng synthetic fixtures hoặc references được phân quyền. `resume token` giúp tiếp tục stream theo contract MongoDB, **không tự trở thành source revision hay global timestamp**.

## 49. Cassandra: lưu gì để tái hiện?

Cassandra cần:
- Keyspace/table schemas, partition/clustering key definitions.
- Datacenter/rack topology, replication strategy/RF.
- Consistency level của từng query.
- Coordinator/replica health và lag theo khả năng quan sát.
- Client timeouts/retry/speculative execution settings.
- Compaction/repair/tombstone conditions.
- Timestamp semantics và client-supplied timestamps nếu có.
- LWT/conditional operation results và concurrency.
- Node restart/network partition schedule.

Một `WriteTimeout` không chứng minh write không được áp dụng. Nếu test quan sát state từ các replicas khác nhau, phải lưu **query consistency và vị trí đọc** để diễn giải kết quả.

## 50. DynamoDB: lưu gì để tái hiện?

Với DynamoDB, ghi:
- Table/index schema và status.
- Region/account scope, capacity mode, autoscaling.
- SDK version, request timeouts và retry settings.
- Read consistency flags, conditional expressions, transaction options.
- Capacity consumption, throttle events và partitions nóng (theo metadata được cung cấp).
- Streams configuration/checkpoints và TTL policy nếu liên quan.
- Fault proxy/client-layer injection, vì operator không điều khiển underlying storage nodes trong managed service.
- Request/operation identity, response/error codes và final table state.

Không tuyên bố tái hiện internal replica scheduling của dịch vụ managed; tập trung vào **contract quan sát được**, workload và fault points kiểm soát được.

## 51. Redis: lưu gì để tái hiện?

Redis phụ thuộc mạnh vào:
- Standalone/Sentinel/Cluster topology.
- Master/replica/slot assignment.
- Persistence RDB/AOF config.
- Replication, failover, memory/eviction, TTL.
- Redis version, client version, connection pool.
- Command mix: GET/SET/INCR/Lua/transactions.
- Network/disconnect/response-drop schedule.
- Key serialization, namespace, hot-key distribution.
- Whether Redis is a cache or authoritative state.

Một `INCR` thành công nhưng reply mất rồi retry có thể nhân counter; replay phải giữ cùng logical operation identity, không chỉ replay raw command bằng một ID mới.

## 52. CouchDB: lưu gì để tái hiện?

CouchDB có revisions, conflicts và `_changes` feed, nên cần:
- Document/design document versions.
- Replication topology và checkpoints.
- Revision IDs/conflict resolution behavior.
- `_changes` sequence values như opaque position theo contract.
- Delete/purge semantics.
- Client retries và update conflict responses.
- Database security policies.
- Thời điểm replication pause/resume.
- Conflict set trước/sau run.

Một document hiện tại trông đúng chưa chứng minh không tồn tại conflict revision hoặc một update bị bỏ qua trong replication.

## 53. Trace, metrics và history có nhiệm vụ khác nhau

| Dữ liệu | Dùng cho | Lưu ý khi tái hiện |
|---|---|---|
| **Correctness history** | Phân tích thao tác, invariants, overlap | Cần đủ coverage trong phạm vi kiểm |
| **Distributed traces** | Chỉ ra đường đi và latency từng tầng | Có thể sampled, thiếu spans |
| **Metrics** | QPS, p99, errors, lag, CPU, retry amplification | Thường không chứa từng op |
| **Database diagnostics** | Slow query, failover, replication, lock/queue | Phụ thuộc engine/version |
| **Audit trail** | Ai đổi cấu hình, bật failpoint, cấp quyền | Cần tách khỏi test noise |
| **Run manifest** | Xác định đầu vào và môi trường | Không mô tả hết lịch chạy thực |

Một biểu đồ p99 bị tăng không tái tạo được một race; một history hoàn chỉnh cũng chưa giải thích CPU/disk bottleneck nếu thiếu system metrics.

## 54. Liên kết artifacts bằng ID ổn định

Có thể gắn:
~~~text
runId
logicalOperationId
attemptId
actorId
faultId
traceId
databaseOperationReference
aggregateVersion
historySegmentId
~~~

Không nên:
- Dùng `traceId` làm bằng chứng auth.
- Dùng broker offset làm logical operationId.
- Dùng shard-local sequence để suy global ordering.
- Dùng raw email/customer ID làm metric label.
- Đổi operationId khi retry cùng business intent.

Nhờ IDs, một điều tra viên có thể mở từ invariant failure → operation history → fault window → trace/database diagnostic → final state.

## 55. Thời gian lưu và bảo mật của gói tái hiện

History có thể chứa thông tin nhạy cảm:
- Keys liên kết với người dùng.
- Tenant resource identifiers.
- Response bodies.
- Query literals.
- Token/credential vô tình bị log.
- Topology/hostname nội bộ.
- Record snapshots và backup.
- Access logs của test identities.

Policy nên:
- Ưu tiên synthetic data.
- Allowlist fields, token hóa keys theo scope cần thiết.
- Không ghi secrets và PII raw.
- Mã hóa transport/storage.
- Hạn chế quyền đọc/export.
- Retention khác nhau giữa failed-run evidence và routine success runs.
- Thêm owner và thời hạn xóa/hold.
- Ghi audit việc truy cập/export gói lỗi nhạy.
- Kiểm copies ở ticket/chat/object storage/backup.

**Tái hiện lỗi không phải lý do lưu vô hạn toàn bộ dữ liệu khách hàng.**

## 56. Tối ưu chi phí mà không làm mất bằng chứng

Có thể áp dụng:
- Success runs: giữ manifest, aggregate metrics, sample diagnostics theo policy.
- Failed runs: giữ history/fault window đầy đủ và một khoảng context trước/sau.
- Kiểm correctness: giữ history đầy đủ của keys/operations dùng để kết luận.
- Dùng compression và versioned binary/JSONL chunks.
- Gắn index theo time range/opId/keyToken/faultId.
- Tránh full payload nếu typed values hoặc fixture refs đủ.
- Chỉ giữ snapshot lớn theo nhu cầu tái hiện đã phê duyệt.

**Không cắt mất các operations trước failure window khi chúng ảnh hưởng state hiện tại.** Một lỗi cuối test có thể bắt nguồn từ update đã xảy ra trước nhiều phút.

## 57. Báo cáo so sánh hai lần chạy

Một bảng so:

| Thành phần | Run A thất bại | Run B tái hiện | Kết luận |
|---|---|---|---|
| Master seed | Giống | Giống | Đầu vào ngẫu nhiên có thể tái sinh |
| PRNG/generator version | Giống | Giống | Các choices dự kiến phù hợp |
| Fixture hash | Khác | Khác | Không so như replay cùng state |
| DB/driver version | Giống | Giống | Không có drift ở version này |
| Replication lag trước fault | 200 ms | 0 ms | Tiền điều kiện khác |
| Fault applied milestone | After commit | Before commit | Chưa tái tạo đúng lỗi |
| Error rate | 2% | 0% | Chỉ là observation |
| Invariant violation | Có | Không | Cần kiểm nguyên nhân khác biệt |

Không ghi “bug đã biến mất” chỉ vì một lần replay không fail. Cần xem **điều kiện nào đã không được tái lập**, và sau đó mới kết luận khả năng đã sửa lỗi.

## 58. Tái hiện thống kê và xác suất

Nếu một lỗi chỉ xuất hiện trong khoảng \(p\) của các lần chạy độc lập có điều kiện tương đương, xác suất **không** thấy lỗi trong \(n\) lần xấp xỉ:

\[
P(\text{no failure in }n)=(1-p)^n
\]

Ví dụ giả định \(p=0{,}1\), chạy 10 lần:
\[
0{,}9^{10}\approx0{,}349
\]

Tức khoảng **34,9% vẫn không gặp lại lỗi** dù xác suất mỗi lần là 10%. Nhưng mô hình này yêu cầu các lần chạy **độc lập và cùng điều kiện**; trong thực tế chúng có thể tương quan vì chung topology, data state, seed family hoặc hạ tầng.

Do đó “chạy lại 10 lần không lỗi” không chứng minh bug đã bị loại bỏ. Nên bổ sung **event-triggered deterministic reproduction** và regression assertions.

## 59. Độ tin cậy khi báo “không tái hiện được”

Có ít nhất bốn trường hợp:
1. **Input khác:** seed, generator, fixtures hoặc config không khớp.
2. **Environment khác:** version, topology, lag, retry hoặc hardware khác.
3. **Schedule khác:** fault và client operations không chồng lấn đúng.
4. **Bug đã sửa:** cùng tiền điều kiện, cùng milestone, nhưng code hiện tại giữ invariant.

Cần tách ba trường hợp đầu khỏi trường hợp thứ tư. Một kết luận “fixed” phải dựa vào bằng chứng regression test phù hợp, không chỉ một green run.

## 60. Quy trình runbook: một test ngẫu nhiên fail

1. Đánh dấu run FAILED và ngừng cleanup phá bằng chứng.
2. Persist seed, effective config và versions nếu chưa được checkpoint.
3. Đóng history, fault log, oracle và metrics segments.
4. Kiểm những artifacts bắt buộc có bị thiếu/gap không.
5. Xác định invariant nào vi phạm và key/operations liên quan.
6. Lấy snapshot/fixture refs theo chính sách bảo mật.
7. Thu hẹp cửa sổ nhân quả, không chỉ vài dòng log gần thời điểm fail.
8. Chạy lại cùng input và fault plan ở môi trường cô lập.
9. Nếu không tái hiện, so config/lag/fault milestone thực tế.
10. Thử barrier/event-triggered fault để khóa race.
11. Lưu cả bản gốc lẫn bản thu nhỏ.
12. Thêm regression test, ghi limitations và owner.

Không “sửa” history gốc để kết quả checker dễ đọc; các nhận định điều tra phải nằm trong bản phân tích riêng.

## 61. Runbook: seed giống nhưng kết quả khác

Kiểm:
- PRNG algorithm/JDK và code commit có giống không?
- Worker count hoặc mapping thay đổi?
- Có shared PRNG bị nhiều threads tranh thứ tự?
- Có call thêm vào PRNG stream chung?
- Input fixtures/TTL/dataset state có khác?
- Load model, actual invoke times, GC/CPU có khác?
- Fault thực được áp đúng milestone?
- Replica leader/lag/consistency có khác?
- Có driver SDK retry tự động?
- Có code path đọc thời gian thật, system entropy hoặc external service?
- Có leftover data từ run cũ?

Một seed có giá trị **để bắt đầu điều tra**, không thay toàn bộ reproducibility package.

## 62. Runbook: history bị thiếu phần cuối

Nếu test JVM crash:
- Đọc manifest đã persisted.
- Liệt kê những history segments đã flush bền.
- Phát hiện invocation không có completion.
- Phân biệt event chưa từng được ghi và event chưa flush.
- Thu server audit/DB state để đối soát nhưng giữ provenance.
- Đánh dấu checkers không đủ dữ liệu là INCONCLUSIVE.
- Điều chỉnh writer buffering/checkpoint policy.
- Chạy lại với failpoint/recording đủ chặt.

Không coi mỗi incomplete operation là failed; nó có thể đã commit trước crash.

## 63. Runbook: kết quả load không còn tương đương

Ví dụ run A ở 2.000 ops/s, run B cùng seed nhưng source CPU quá cao khiến thực tế chỉ nhận 900 ops/s.

Kiểm:
- Offered vs actual logical rate.
- In-flight queues và client saturation.
- Driver connection pools và timeout.
- Retry amplification.
- Workload distribution và key hotness.
- Disk/compaction/cache cold.
- JVM heap/GC và warm-up.
- Autoscaling/failover state.
- Time windows dùng đo p99.
- Fault severity/duration.

Khi các tiền điều kiện khác lớn, **không kết luận thay đổi code làm hiệu năng tốt/xấu** chỉ bằng hai con số p99.

## 64. Checklist một gói tái hiện có ích

~~~text
[ ] Run ID duy nhất và owner/case reference.
[ ] Seed được persist trước workload.
[ ] PRNG algorithm/generator version được ghi.
[ ] Per-worker seed mapping và worker count.
[ ] Effective config, timeouts/retries/consistency.
[ ] DB/driver/app/test-tool versions + image digests.
[ ] Topology và trạng thái ban đầu (lag/health).
[ ] Fixture/snapshot/data generator reference + checksum.
[ ] Scheduled operations và actual invocation/completion.
[ ] Retry attempts và logical operation identity.
[ ] Failure point plan và fault actually applied.
[ ] Timebase, clock offsets và causal milestones.
[ ] Unknown outcomes không bị ép thành failed.
[ ] Oracle/readback và các bất biến đã kiểm.
[ ] History coverage/gap/dropped event metrics.
[ ] Offered/completed QPS, p99, retries, lag.
[ ] Hướng dẫn dựng môi trường clean và lệnh replay.
[ ] Checksum/integrity của artifacts.
[ ] Secret/PII minimization, permissions, retention.
[ ] Run status: PASS, FAIL, INCONCLUSIVE theo evidence.
~~~

Các checkbox là khuôn mẫu học tập, không thay quy trình QA bài viết trong pipeline sản xuất nội dung.

## 65. Những nhầm lẫn thường gặp

| Nhầm lẫn | Vì sao sai | Cách đúng |
|---|---|---|
| Lưu seed là tái hiện 100% | Thread/network scheduling đổi | Lưu history, fault milestones |
| Seed giống thì PRNG giống | Thuật toán/version khác | Ghi algorithm và runtime |
| Dùng PRNG chung cho threads | Consumption order không ổn định | Separate per-worker streams |
| Thêm một random call không ảnh hưởng | Dịch chuyển toàn chuỗi | Domain-separated seeds |
| Không cần data fixture hash | State ban đầu khác | Snapshot/fixture reference |
| Run ID cũng là seed | Vai trò khác | Unique run ID, repeatable seed |
| File config gốc là effective config | Env/flags override | Persist resolved config |
| `latest` đủ cho binary | Version đổi theo thời gian | Commit/image digests |
| Lỗi lúc t=60s luôn cùng mốc | Scheduling khác | Event-based fault triggers |
| Có fault plan nghĩa đã chèn lỗi | Controller có thể fail | Fault applied history |
| Drop connection bảo đảm sau commit | Request có thể chưa tới | Hook theo commit milestone |
| Completion order là invoke order | Operations chồng lấn | Intervals invoke/complete |
| Timestamp các hosts so trực tiếp | Clock skew | Causal/sequence evidence |
| nanoTime toàn hệ cùng gốc | Chỉ có ý nghĩa trong process | Per-process timebases |
| Timeout là write rollback | Commit outcome UNKNOWN | Readback/reconcile |
| Không thấy data là chưa ghi | Replica/cache stale | Consistency-aware oracle |
| Một trace sampled đủ linearizability | Missing operations gây sai | Complete correctness scope |
| Count đúng nghĩa không corrupt | Values/versions có thể sai | Semantic invariants |
| Test data lần trước không sao | Duplicates/TTL tồn dư | Clean fixture isolation |
| Instrumentation không ảnh hưởng | I/O/GC/scheduling đổi | Measure observer overhead |
| History fail nên sửa thành success | Xóa quan sát thực | Reconciliation riêng |
| Không thấy lại lỗi = fixed | Conditions có thể khác | Compare preconditions |
| Mười run xanh chứng minh chắc | Lỗi xác suất hiếm | Statistics + deterministic hooks |
| p99 thấp hơn nghĩa tốt hơn | Offered load khác | Compare equivalent workloads |
| Metrics đủ để debug race | Không có per-op order | History + traces |
| Bao nhiêu log cũng vô hại | Cost/PII/latency | Minimal secure artifacts |
| Checksum nghĩa test đúng | Chỉ integrity bytes | Oracle/invariants |
| Managed NoSQL không thể kiểm lỗi | Không điều khiển node nội bộ | Contract/fault proxy tests |
| Redis INCR reply mất thì chưa tăng | Lệnh có thể đã chạy | Idempotency/ledger |
| Cassandra timeout là rollback | Replicas có thể đã apply | Scope-aware consistency |
| Một MongoDB resume token là clock toàn cục | Opaque source cursor | Theo API contract |
| Bản test thu nhỏ thay hoàn toàn bản gốc | Có thể mất context | Preserve both histories |

## 66. Bài tập thực hành

### Bài tập 1 — Manifest tối thiểu

Hãy thiết kế YAML manifest cho test `checkout-failover` với run ID, seed, engine/driver version, consistency, fault plan, input fixture hash và history reference. Chỉ ra những field không được chứa secrets.

### Bài tập 2 — Các mức tái hiện

So sánh deterministic input replay, causal/event-driven replay và statistical reproduction. Cho một ví dụ NoSQL cần từng mức.

### Bài tập 3 — PRNG khác thuật toán

Hai run đều seed=42 nhưng một bên dùng `Random`, một bên dùng `SplittableRandom`. Vì sao chuỗi operation không giống? Phải lưu metadata nào?

### Bài tập 4 — Shared generator

Bốn Java threads cùng gọi một PRNG. Thiết kế per-worker seed derivation để chạy lại đầu vào dù scheduler khác thứ tự.

### Bài tập 5 — Domain separation

Một engineer thêm lần random chọn payload làm lịch fault đổi toàn bộ. Hãy tách seedData, seedFaults, seedWorkload và lập test chứng minh luồng lỗi không phụ thuộc việc sinh data.

### Bài tập 6 — Run ID khác seed

Một lần replay cùng seed bị duplicate keys do data run cũ. Đề xuất namespace/reset strategy giữ input logic tương đương.

### Bài tập 7 — Effective config

Ứng dụng nạp YAML, env vars, CLI và feature flags. Thiết kế cơ chế lưu resolved config và dấu vết override mà không ghi secrets.

### Bài tập 8 — Version drift

Hai runs có cùng seed nhưng khác JDK build, driver retry policy và MongoDB server version. Cần so và khôi phục những dependency nào trước khi kết luận bug fixed?

### Bài tập 9 — Workload distribution

Hai tests cùng 2.000 ops/s nhưng một test uniform keys và một test Zipf-like hot keys. Vì sao p99 khác? Đưa distribution parameters vào manifest.

### Bài tập 10 — Open-loop/closed-loop

Giải thích vì sao closed-loop có thể làm QPS giảm khi database quá tải. Viết các metrics cần để so hai lần chạy công bằng.

### Bài tập 11 — Scheduled vs actual

Generator định gửi request lúc 10, 12, 14 ms, nhưng GC pause khiến lần thực là 10, 20, 20 ms. Những timestamps nào cần ghi và vì sao?

### Bài tập 12 — Fault plan vs fault applied

Controller dự kiến restart node B lúc 60 giây nhưng lệnh thất bại. Báo cáo cần phản ánh gì để không tuyên bố đã kiểm failover?

### Bài tập 13 — Failpoint theo milestone

Thiết kế fault sau durable commit trước HTTP reply. Vì sao `sleep 100ms` rồi kill pod không mô phỏng cùng ranh giới?

### Bài tập 14 — JSONL history

Viết bốn dòng invoke/complete cho một write và một read có overlap. Giải thích khi nào read trả giá trị cũ là hợp lệ.

### Bài tập 15 — Unknown outcome

Client timeout, oracle ban đầu chưa thấy record nhưng về sau thấy. Hãy lưu kết quả quan sát theo thời gian mà không sửa sự thật `CLIENT_TIMEOUT`.

### Bài tập 16 — Monotonic clock

Giải thích vì sao `System.nanoTime()` phù hợp đo latency trong một JVM nhưng không được dùng trực tiếp để so timestamp giữa hai JVM.

### Bài tập 17 — Linearizability

Register ban đầu 0; write(1) complete trước read() invoke; read trả 0. Phân tích nếu contract là linearizable và nếu read từ follower eventual.

### Bài tập 18 — Missing history

Một worker crash khi còn ba invocations chưa complete. Chọn cách lưu/diễn giải để checker không kết luận sai.

### Bài tập 19 — History sampling

Một team muốn chỉ giữ 1% operations rồi chạy linearizability checker trên history sampled. Nêu rủi ro và thay bằng scope correctness có capture đầy đủ.

### Bài tập 20 — Fixture hash

Cùng seed nhưng dữ liệu đầu vào đã thay index, TTL và phân bố tenant. Cần lưu/checksum những artifacts nào để đánh giá hai lần chạy có tương đương?

### Bài tập 21 — Replay lost update

Dùng hai workers và barrier buộc cả hai đọc `balance=100` trước khi cập nhật. Mô phỏng write race và thiết kế CAS regression test.

### Bài tập 22 — Retry sau mất response

Một lệnh order commit rồi phản hồi bị drop. Ghi operationId, fault event, attempts, readback và invariant chống duplicate order/payment.

### Bài tập 23 — MongoDB failover

Thiết kế run record cho primary step-down: read/write concern, retryable writes, node roles, replication lag, driver behavior và operation history.

### Bài tập 24 — Cassandra timeout

Với RF=3 và consistency level cụ thể, mô phỏng coordinator timeout. Lưu các quan sát nào để phân biệt unknown commit và stale read?

### Bài tập 25 — DynamoDB conditional write

Một request PutItem có condition, SDK retry sau lỗi mạng. Thiết kế history, condition result và kiểm state không nhân logical effect.

### Bài tập 26 — Redis INCR

Redis đã tăng counter nhưng reply mất. Tái hiện bằng proxy và đưa ra test chứng minh nguy cơ double increment rồi cách thêm operation ledger.

### Bài tập 27 — CouchDB revisions

Một replication job tạo conflict revisions. Cần lưu `_rev`, change checkpoints, conflict set và retry history nào để tái hiện kết quả?

### Bài tập 28 — Observer effect

Một test fail khi history writer bất đồng bộ nhưng không fail khi ghi synchronously. Giải thích tác động của instrumentation lên scheduling và cách giữ đủ bằng chứng.

### Bài tập 29 — Xác suất không gặp lại lỗi

Giả sử xác suất fail mỗi run là 10% và các runs độc lập. Tính xác suất không gặp trong 10 lần; giải thích vì sao giả định độc lập có thể sai ở cụm NoSQL thật.

### Bài tập 30 — Retention/privacy

Một history chứa raw customer ID, token và response payload. Thiết kế synthetic fixture, allowlist, encryption, RBAC, retention, signed manifest và incident artifact access.

### Bài tập 31 — Run B không tái hiện lỗi

Run A fail còn Run B cùng seed green. Nhưng fixture hash và fault trigger khác. Viết báo cáo nêu đúng limitations và kế hoạch thử lại.

### Bài tập 32 — Thiết kế hệ thống tổng hợp

Một nền tảng dùng Java/JUnit, MongoDB orders, DynamoDB profiles, Cassandra events, Redis cache và một broker. Hãy thiết kế:

1. Effective run config và version pinning.
2. Master/per-worker/data/fault seeds.
3. Synthetic fixtures/snapshot và checksum.
4. Logical command/attempt IDs.
5. Full correctness history và metric/tracing policies.
6. Clock domains, invocation intervals, causal barriers.
7. Fault plan, applied records và event-triggered hooks.
8. Idempotency, readback oracle, transaction/consistency model.
9. Controlled replay và shrinking.
10. Security/retention, manifest signing và report limitations.

### Bài tập 33 — Phê bình thiết kế thiếu tái hiện

Một nhóm đề xuất:

~~~text
Chỉ lưu "seed=42".
Cấu hình lấy bản mới nhất từ Git mỗi lần chạy lại.
Dùng một Random chung cho 64 threads.
Không lưu initial data, index hoặc TTL.
Inject lỗi bằng sleep rồi kill node ngẫu nhiên.
Lưu duy nhất thứ tự hoàn thành, bỏ invocation.
Dùng timestamps từ mọi JVM như một clock chung.
Mọi timeout được ghi "write failed".
Chỉ giữ 1% history để kiểm linearizability.
Nếu chạy lại không lỗi thì đóng bug.
Lưu raw request/response của khách hàng vô thời hạn.
~~~

Hãy chỉ ra từng lỗi và viết lại **reproducibility package** với config hiệu lực, PRNG streams, data fixture, operation/fault histories, oracle, causal replay và giới hạn privacy.

---

**Kết luận:** Trong kiểm thử lỗi và tải của NoSQL, một kết quả chỉ thực sự hữu ích khi có thể **giải thích và thử lại bằng bằng chứng đủ**. Cần lưu **cấu hình đã có hiệu lực, phiên bản mã/driver/database, trạng thái cụm, seed và thuật toán PRNG, mapping workers, fixtures, lịch thao tác invoke/complete, fault plan và fault thực sự xảy ra, readback oracle cùng invariants**. Seed giúp tái tạo lựa chọn đầu vào nhưng không điều khiển mọi interleaving; những lỗi race, timeout sau commit hay failover cần **causal barriers, failpoints theo sự kiện và history bảo toàn UNKNOWN outcomes**. Một gói tái hiện có checksum, quyền truy cập và retention rõ ràng giúp phân biệt bug thật với drift môi trường, giảm thời gian điều tra và biến thất bại hiếm thành regression test hữu ích mà không làm lộ dữ liệu nhạy cảm.
