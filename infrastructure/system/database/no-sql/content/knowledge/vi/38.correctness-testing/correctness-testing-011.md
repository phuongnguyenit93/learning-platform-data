# Property-based testing hoặc mô hình trạng thái cho thao tác dữ liệu

Trong **Database No SQL**, kiểm thử thao tác dữ liệu không chỉ là gửi một lệnh `insert` rồi kiểm tra đã đọc được record. Ứng dụng thường phải xử lý **schema linh hoạt, partition keys, truy vấn phân trang, cập nhật có điều kiện, TTL, retries, ghi đồng thời, replication và xử lý event bất đồng bộ**. Những tình huống lỗi khó nhất thường không đến từ một lệnh đơn lẻ mà từ **các chuỗi thao tác** hoặc cách các lệnh xen kẽ dưới network delay, crash và timeout.

Ví dụ một dịch vụ Java quản lý tồn kho:

~~~text
Inventory SKU-101 available = 1

Client A reads available=1
Client B reads available=1
A reserves 1
B reserves 1
```

Một unit test bình thường kiểm tra `reserve(1)` trả thành công khi còn hàng không bắt được lỗi **oversell**. Ngược lại, một test tự chạy hai threads một lần rồi không gặp race không chứng minh implementation an toàn.

**Property-based testing (PBT)** tạo nhiều input có cấu trúc và kiểm những tính chất phải đúng với mọi input hợp lệ. **Model-based/stateful testing** định nghĩa một mô hình trạng thái đơn giản, sau đó so hành vi hệ thật với mô hình qua những **chuỗi lệnh** được sinh và rút gọn tự động. Khi cần kiểm consistency phân tán, có thể mở rộng sang **concurrent history, fault injection và linearizability/serializability checks**, nhưng phải hiểu giới hạn và bảo đảm thực sự của hệ lưu trữ.

Bài thuộc chương **Kiểm thử tính đúng** của **Database No SQL**, với các mục tiêu:

- Viết **invariant** thay vì chỉ viết các `assert` cho vài ví dụ cố định.
- Thiết kế **generator** cho key, document, sequence, concurrent commands và trường hợp biên.
- Dùng **reference model**, *command preconditions*, *postconditions* và **shrinking** để tìm counterexample nhỏ nhất.
- Thực hành với **Java/JUnit/jqwik** và các ví dụ độc lập với engine.
- Chọn đúng **consistency model** khi kiểm Cassandra, MongoDB, DynamoDB, Redis, CDC, search projection.
- Kiểm transaction, CAS, idempotency, TTL, pagination, tombstone, version và eventual convergence.
- Ghi lại seed, lịch sử, phiên bản, môi trường và fault timeline để tái hiện lỗi, rồi đưa những lỗi ấy vào regression suite.

Các đoạn code được phân thành **ví dụ có thể chạy khi có dependencies phù hợp**, **skeleton/pseudocode** và **kịch bản test hệ phân tán**. Không tự coi framework chạy được một property là bằng chứng hệ an toàn dưới mọi failure model.

> **Nguyên tắc cốt lõi:** Model được dùng làm nguồn dự đoán hành vi **độc lập** với implementation; property phải phản ánh **hợp đồng dữ liệu và consistency thực sự**, chứ không chỉ điều ta mong database thực hiện.

---

## 1. Vì sao ví dụ kiểm thử cố định chưa đủ?

Một bộ kiểm thử truyền thống có thể gồm:

~~~text
createUser -> status CREATED
getUser -> returns user
updateEmail -> email changed
deleteUser -> get returns 404
~~~

Đó là những tests quan trọng. Nhưng không bao phủ hết:

- Hai users khác tenants dùng cùng `userId`.
- Chuỗi `create → delete → recreate → stale update`.
- Update có `expectedVersion` lỗi thời.
- Request timeout sau khi DB commit.
- `get` từ replica chưa bắt kịp.
- Pagination khi có insert/delete đồng thời.
- Duplicate CDC event từ broker.
- Document có null/missing fields hoặc tên Unicode.
- TTL đã qua nhưng physical delete chưa chạy.
- Tranh chấp trên một hot partition key.

PBT mở rộng **không gian input**; state model mở rộng **không gian lịch sử thao tác**.

## 2. Testing ví dụ, PBT và model-based test

| Cách kiểm thử | Input | Oracle | Điểm mạnh |
|---|---|---|---|
| Example-based | Vài trường hợp do người viết chọn | Expected value cụ thể | Dễ đọc, tốt cho regression |
| Property-based | Nhiều giá trị sinh theo domain | Quy luật/invariant | Tìm edge cases ít nghĩ tới |
| Stateful/model-based | Chuỗi commands sinh theo trạng thái | Reference transition model | Tìm lỗi giữa nhiều thao tác |
| Concurrency history test | Operations xen kẽ giữa workers | Consistency/linearizability checker | Tìm race và order bugs |
| Fault-injection test | Crash, partition, timeout, pause | Safety/liveness model | Tìm lỗi khi hệ suy giảm |

Các cách này **bổ sung lẫn nhau**. Một test property nên tạo regression cụ thể khi phát hiện bug; model testing cũng cần unit tests cho chính model/oracle.

## 3. Property là gì?

Một **property** là phát biểu về hành vi mong đợi trên một tập input hợp lệ.

Ví dụ hàm chuẩn hóa key:

\[
\forall x\in D,\quad normalize(normalize(x))=normalize(x)
\]

Đó là **tính idempotent** của normalizer.

Với thao tác dữ liệu:

~~~text
For every tenant T and document D:
  after an acknowledged create of D under T,
  an authorized read under T returns a state consistent
  with the read-consistency contract.
~~~

Phần cuối rất quan trọng: **không được tự thêm linearizable read** nếu datastore chỉ bảo đảm eventual consistency cho read path đang test.

## 4. Invariant khác expected example

Ví dụ:

~~~text
reserve(stock=10, qty=3) -> remaining=7
```

là một expected example.

Một invariant:

\[
available\ge0
\]

trong một hệ không cho âm kho, và:

\[
available+reserved+sold=initialStock+restocked
\]

nếu toàn bộ các trạng thái và nghiệp vụ được mô hình hóa bằng những đại lượng đó.

Invariant có thể đúng **qua hàng nghìn sequence** không cần biết mọi giá trị ban đầu. Tuy nhiên, phải định nghĩa rõ trường hợp cancellation, restock, refunds, partial fulfillment, returns; một conservation equation sai domain sẽ gây test false positives.

## 5. Phạm vi bất biến

Có nhiều mức:

- **Local record invariant:** `quantity >= 0`, `version >= 0`.
- **Per-aggregate invariant:** trạng thái Order không quay từ `PAID` về `PENDING` nếu business state machine cấm.
- **Cross-document invariant:** tổng các reservations không vượt source inventory.
- **Per-tenant invariant:** tenant A không đọc/ghi được tài nguyên tenant B.
- **Event pipeline invariant:** mỗi payment intent chỉ có tối đa một business charge.
- **History invariant:** các operations có thứ tự quan sát phù hợp consistency model.
- **Liveness property:** khi hệ phục hồi, pending work cuối cùng được xử lý trong điều kiện đã định.

Không ép invariant vượt phạm vi atomicity mà engine không bảo đảm. Nếu một cross-document invariant thật sự bắt buộc, architecture phải dùng transaction/aggregation/coordination thích hợp.

## 6. Safety và liveness khác nhau

**Safety**: điều sai không xảy ra.

~~~text
No two successful reservations consume the same last item.
A stale version never overwrites a newer one.
A deleted user never leaks into another tenant.
~~~

**Liveness**: điều mong muốn cuối cùng xảy ra nếu đủ điều kiện.

~~~text
A retryable operation eventually finishes when the DB recovers.
CDC projection eventually catches up after traffic quiesces.
A crashed queue worker's job can be reassigned.
~~~

PBT tuần tự dễ kiểm safety. Liveness cần **bounds, fairness assumptions, thời gian chạy đủ, scheduler/fault model**; không thể chứng minh bằng `Thread.sleep(1000)` duy nhất.

## 7. Reference model: mô hình nhỏ dễ tin

Một model tốt chỉ mô tả **hợp đồng nghiệp vụ**, không sao chép chi tiết triển khai NoSQL.

Ví dụ model cho một inventory item:

~~~text
State:
  available
  reserved
  version
  processedOperationIds

Commands:
  restock(operationId, qty)
  reserve(operationId, qty)
  release(operationId, qty)
  get()
```

Model có thể dùng `Map`/`BigInteger` trong bộ nhớ, còn SUT (*System Under Test*) dùng DynamoDB conditional writes hoặc MongoDB transactions.

**Độc lập implementation** rất quan trọng: nếu model copy cùng một câu truy vấn lỗi từ SUT, cả hai có thể trả cùng kết quả sai và test giả tạo pass.

## 8. State transition được định nghĩa rõ

Một reservation đơn giản với \(q>0\):

\[
reserve(s,q)=
\begin{cases}
(available-q,\ reserved+q,\ version+1),&available\ge q\\
s,&available<q
\end{cases}
\]

Điều kiện:

- Reservation thành công chỉ khi đủ số lượng.
- Reservation thất bại không đổi state.
- Version tăng nếu và chỉ nếu có mutation được commit (theo contract).
- `available` không âm.
- Nếu operation ID đã xử lý, replay trả consistent outcome mà không trừ kho lần hai.

Đây là **một contract mẫu**, không phải mô tả tất cả cách tính stock thật (có thể tồn tại pending/sold/backordered).

## 9. Model nhỏ nhưng bao phủ phân biệt quan trọng

Một model quá sơ sài:

~~~text
Map<Id, Object>
```

có thể bỏ mất:

- Tenant scoping.
- Per-record version.
- Tombstones.
- TTL expiry.
- ExpectedVersion.
- Duplicate operation IDs.
- Business status transitions.
- Search projection staleness.

Mô hình tối thiểu tốt nên giữ đủ trạng thái cho **các bất biến đang kiểm**, nhưng không mang toàn bộ cache driver, connection pool hoặc replication topology nếu chúng không ảnh hưởng property.

## 10. Command là đơn vị sinh lịch sử

Một command cần mô tả:

- Tên thao tác (`Create`, `Update`, `Delete`, `Read`).
- Các arguments: tenant, key, quantity, version, operation ID.
- Preconditions hợp lệ, hoặc deliberately invalid.
- Expected model transition.
- Operation SUT tương ứng.
- Outcome categories.
- Postcondition.
- Cách log/shrink khi fail.

Ví dụ:

~~~text
Create(T1, K7, payload=v1)
Update(T1, K7, expectedVersion=1, payload=v2)
Update(T1, K7, expectedVersion=1, payload=v3) -> conflict
Delete(T1, K7, expectedVersion=2)
Read(T1, K7) -> missing/deleted according to contract
~~~

## 11. Preconditions không nên loại bỏ mọi lỗi

Stateful generator có thể chỉ sinh:

~~~text
Update(key) only if key exists
```

Nếu chỉ test “happy path”, bỏ qua những lỗi thực tế quan trọng:

- Update nonexistent key.
- Wrong expectedVersion.
- Duplicate create.
- Delete twice.
- Read after delete.
- Invalid tenant.
- Oversized document.
- Expired idempotency key.
- Retry after unknown commit.

Tốt hơn là **cố ý sinh cả valid và invalid commands**, với expected failure outcome rõ và model không bị thay đổi sau failure.

## 12. Cần xác định outcome taxonomy

Một API có thể trả:

~~~text
CREATED
UPDATED
NOT_FOUND
VERSION_CONFLICT
ALREADY_APPLIED
BUSINESS_REJECTED
UNAUTHORIZED
RETRYABLE_TIMEOUT
UNKNOWN_COMMIT_OUTCOME
```

Không nên xem mọi exception là lỗi correctness. Một `VERSION_CONFLICT` được mong đợi khi `expectedVersion` cũ; một `UNKNOWN_COMMIT_OUTCOME` nghĩa là client chưa thể xác nhận apply hay chưa.

Model/oracle cần phân biệt:

- **Definite success**.
- **Definite no-op/rejection**.
- **Ambiguous outcome**.
- **Transient infrastructure failure**.
- **Protocol violation**.

Việc biến timeout thành “đã thất bại nên không thay đổi state” là một lỗi rất phổ biến trong stateful testing của NoSQL.

## 13. Test deterministic transformation trước

Các hàm thuần (pure) dễ được kiểm bằng PBT:

- Serialize/deserialize schema.
- Canonicalize document keys.
- Encode/decode pagination cursor.
- Transform v1 → v2.
- Encode/decode encrypted envelope metadata.
- Merge projections.
- Generate query/filter from inputs.
- Convert TTL seconds/milliseconds.

Ví dụ:

\[
decode(encode(x))=x
\]

với \(x\) thuộc tập dữ liệu **được phép biểu diễn** theo schema.

Không dùng universal equality nếu decoder chủ động chuẩn hóa số/thời gian hoặc bỏ trường không thuộc contract.

## 14. Generators phải phản ánh domain

Một generator documents có thể tạo:

- IDs ngắn/dài.
- Unicode gồm dấu tiếng Việt và ký tự kết hợp.
- Empty string, whitespace, null/missing theo policy.
- Nested maps/lists.
- Decimal/large integers.
- Field names hợp lệ/không hợp lệ.
- Tenant IDs và composite keys.
- Timestamp trước/sát/sau TTL.
- Versions 0/1/MAX và stale values.
- Payload rất nhỏ/gần size limit.
- Duplicate IDs.
- Deleted/tombstone records.

**Random hoàn toàn** không đồng nghĩa coverage tốt; input distribution phải chủ động chạm boundaries mà hệ dễ lỗi.

## 15. Generator không được giấu assumptions

Ví dụ test:

~~~text
For all tenant IDs from "A" to "Z" and positive quantities 1..100
```

không kiểm:

- Tenant `é`, `Đà Nẵng`.
- Quantity `0`/negative nếu API có invalid-input behavior.
- Large overflow values.
- Missing tenant.
- Collision sau key normalization.

Nên ghi rõ **input domain đã được test** và version hóa generators cùng schema, tránh nghĩ “10.000 random cases” nghĩa là bao phủ mọi dữ liệu.

## 16. Seed và reproducibility

PBT generator thường dùng seed để có thể tái hiện sequence thất bại.

Một báo cáo có ích:

~~~text
property: inventory_reserve_does_not_oversell
seed: 79832241
attempt: 207
shrunk:
  initialStock=1
  reserve(A, 1)
  reserve(B, 1)
observed: both reservations succeed
```

Cần lưu:

- Seed, sample/iteration.
- Shrunk counterexample.
- SUT/DB/driver version.
- Topology, consistency, indexes.
- Time/fault injection decisions.
- Test isolation identifiers.
- Request IDs và transaction/history logs.

**Seed không đủ** để tái hiện lịch interleaving thread hoặc network; cần recorded schedule/history hoặc deterministic scheduler khi khả thi.

## 17. Shrinking: tìm phản ví dụ nhỏ nhất

Một failure sau 300 commands khó debug:

~~~text
Create, Read, Update, Delete, Query, ...
```

**Shrinking** thử giảm input trong khi giữ failure:

- Bớt commands không cần.
- Giảm số tenants/keys.
- Giảm quantity.
- Rút ngắn strings/documents.
- Thu hẹp thời gian giữa operations.
- Đơn giản hóa concurrency schedule.
- Bớt lỗi mạng không liên quan.

Ví dụ counterexample tối giản:

~~~text
State: stock=1
A reserve(1) -> SUCCESS
B reserve(1) -> SUCCESS
Invariant available >= 0 fails
```

**Shrunk trace** thường hữu ích cho regression hơn một seed dài khó tái hiện.

## 18. Shrinking cần giữ các tiền điều kiện

Nếu shrink một history làm mất command `Create(K)` nhưng giữ `Update(K)`, test có thể chuyển từ race bug sang `NOT_FOUND` bình thường.

Một stateful shrinker cần:

- Re-run model để xác nhận preconditions.
- Hoặc cho invalid commands với oracle tương ứng.
- Giữ dependency giữa event/source version.
- Giữ happens-before constraints trong concurrent history.
- Giữ tenant/key mapping.
- Không biến failure loại A thành failure loại B rồi báo nhầm.

Shrinking tốt **bảo toàn ý nghĩa của phản ví dụ** trong contract.

## 19. Coverage không chỉ bằng số samples

Các chỉ số hữu ích:

- Số valid/invalid commands.
- Tần suất stale version conflict.
- Số sequences dài/short.
- Tỷ lệ duplicate keys/operation IDs.
- Tombstone/TTL boundary cases.
- Số cross-tenant denial attempts.
- Tỷ lệ network ambiguity.
- Số transitions state machine được đi qua.
- Interleaving/fault classes đã kiểm.
- Source/target consistency modes.

10.000 tests chỉ sinh `Create` trên keys mới có thể thua 200 sequences có chủ đích `Create→Update→Delete→Retry`.

## 20. Property sai có thể gây false positives

Ví dụ:

~~~text
After write returns success, every replica must immediately read new value.
```

Sai nếu API read từ eventually consistent replica không cam kết read-your-writes.

Nên viết:

~~~text
After a write acknowledged under policy X,
a read using consistency mode Y must satisfy
the documented guarantee for X and Y.
```

Với eventual consistency, có thể kiểm **eventual convergence** khi không có thêm writes, network heal, thời gian/retention hợp lệ và fairness; không áp immediate equality không có trong contract.

---

## 21. Java: khởi đầu bằng jqwik

**jqwik** là framework property-based testing cho JVM, tích hợp với JUnit Platform. API cụ thể có thể thay đổi theo phiên bản; ví dụ sau thể hiện cấu trúc thông dụng.

Ví dụ Maven dependency (chọn một bản phù hợp project/test runner, không dùng số version này như cam kết bản mới nhất):

~~~xml
<dependency>
  <groupId>net.jqwik</groupId>
  <artifactId>jqwik</artifactId>
  <version>${jqwik.version}</version>
  <scope>test</scope>
</dependency>
~~~

`${jqwik.version}` là property Maven người dùng khai báo theo phiên bản đã chọn; không phải literal version hoàn chỉnh. Với Gradle, cần `testImplementation` cho artifact và cấu hình JUnit Platform theo build tool version.

## 22. Property thuần: round-trip encode/decode

Một ví dụ hoàn chỉnh dùng Java URL-safe Base64 để test codec byte array:

~~~java
import net.jqwik.api.*;
import java.util.Base64;
import java.util.Arrays;
import static org.junit.jupiter.api.Assertions.*;

class CodecProperties {
    @Property(tries = 500)
    void base64UrlRoundTrip(
            @ForAll byte[] payload) {

        String encoded = Base64.getUrlEncoder()
            .withoutPadding()
            .encodeToString(payload);

        byte[] decoded = Base64.getUrlDecoder()
            .decode(encoded);

        assertArrayEquals(payload, decoded);
    }
}
~~~

Property này là ví dụ minh họa PBT cho **hàm thuần**, chưa phải kiểm NoSQL. Nó giúp luyện cú pháp `@Property`, `@ForAll`, generated input và failure shrinking trước khi kết nối database.

Lưu ý generator mặc định cho arrays có distribution riêng; muốn gần payload size limit phải tự thêm generator/boundary cases.

## 23. Property: normalization idempotence

Giả sử ứng dụng định nghĩa `normalizeEmail` để tạo lookup key. Một contract có thể yêu cầu:

\[
normalize(normalize(e))=normalize(e)
\]

Ví dụ Java (hàm nghiệp vụ được cung cấp bởi ứng dụng):

~~~java
import net.jqwik.api.*;
import static org.junit.jupiter.api.Assertions.*;

class EmailNormalizationProperties {
    @Property(tries = 1000)
    void normalizationIsIdempotent(
            @ForAll("candidateEmails") String email) {
        String once = EmailKeys.normalize(email);
        String twice = EmailKeys.normalize(once);
        assertEquals(once, twice);
    }

    @Provide
    Arbitrary<String> candidateEmails() {
        return Arbitraries.strings()
            .withChars('a', 'b', 'c', 'A', 'B', 'C',
                       '0', '1', '.', '+', '-', '@')
            .ofMinLength(1)
            .ofMaxLength(80);
    }
}
~~~

`EmailKeys.normalize` là domain method giả định. Test này **không chứng minh normalize đúng email chuẩn quốc tế**; generator cố tình hạn chế ký tự để minh họa, và cần thêm Unicode/invalid cases theo contract.

## 24. Generator độc lập với SUT

Không nên lấy toàn bộ input generator bằng:

~~~text
SUT.generateValidDocument()
```

rồi test `SUT.save` với output của chính SUT. Nếu generator của SUT sai, test sẽ bỏ luôn các trường hợp sai.

Thay vào đó:

- Generator riêng theo **hợp đồng/schema**.
- Explicit invalid records.
- Canonical domain value objects.
- Boundary values và edge-case corpora.
- Seeded randomized cases.
- Fuzzed payloads nếu cần.
- Differential check với implementation độc lập.

Model/generator không nhất thiết cùng ngôn ngữ với production application.

## 25. Arbitraries và `@Provide`

Một generator có cấu trúc:

~~~java
import net.jqwik.api.*;

record UpsertInput(String tenant, String key, int version) {}

class InputGenerators {
    @Provide
    Arbitrary<UpsertInput> upserts() {
        Arbitrary<String> tenants =
            Arbitraries.of("tenant-A", "tenant-B", "tenant-C");

        Arbitrary<String> keys =
            Arbitraries.of("k1", "k2", "k3");

        Arbitrary<Integer> versions =
            Arbitraries.integers().between(0, 10);

        return Combinators.combine(tenants, keys, versions)
            .as(UpsertInput::new);
    }
}
~~~

Dùng tập nhỏ keys là **chủ đích tăng va chạm**, giúp dễ sinh duplicate key và stale update. Khi test schema thật, có thể thêm long/random keys hoặc special characters; đừng chỉ dùng random UUID hoàn toàn vì xác suất đụng key thấp.

## 26. Kiểm output của transformer

Ví dụ event v1 có:

~~~json
{
  "tenantId": "t1",
  "orderId": "o1",
  "amount": "120.50",
  "currency": "VND"
}
~~~

Transformer v2 có thể chuẩn hóa đơn vị tiền, currency code và key.

Một property cần xác định rounding và giới hạn:

~~~text
For every valid V1 document:
  transformV1ToV2 returns a V2 document
  with the same tenant identity and source operation ID.
```

Có thể bổ sung:

- Không làm mất các trường mandatory.
- Total monetary amount giữ nguyên theo đơn vị chuẩn.
- Key mapping deterministic.
- Không tạo raw PII ở projection không có quyền.
- `sourceVersion` không giảm.
- TTL/expiry semantics giữ nguyên.

Không tự dùng `double` cho tiền nếu domain cần exact decimal arithmetic.

## 27. Metamorphic testing khi không có expected result trực tiếp

Đôi khi khó biết một query phức tạp phải trả toàn bộ records nào cho input ngẫu nhiên, nhưng có những quan hệ giữa các lần chạy:

- Chạy query với filter bổ sung không được trả **thêm** records ngoài tập ban đầu (theo snapshot/consistency phù hợp).
- Thêm một document không match filter không làm thay kết quả query trên một dataset bất biến.
- Phân trang hết tất cả pages phải bằng kết quả full query với cùng snapshot/ordering.
- Encode rồi decode cursor giữ cùng continuation semantics.
- Reapplying cùng idempotent upsert không đổi final state.
- Hai biến thể serialization hợp lệ cho cùng logical document phải normalize về cùng domain state.

Đây là **metamorphic properties**. Chúng vẫn cần preconditions; với live dataset thay đổi giữa hai reads, set-inclusion có thể không giữ.

## 28. Property cho pagination

Trong một dataset cố định \(D\), query có stable total order \(<\) theo composite key:

\[
concat(pages(D))=sort_{<}(filter(D))
\]

Ngoài ra:

- Không duplicate keys.
- Không skip records.
- Page sizes trong giới hạn API.
- Cursor tiến triển (không infinite loop).
- Mọi record tuân filter/tenant.
- `nextCursor` tương thích query config/version.

Không kiểm property này trên một live dataset đang được ghi song song mà không có snapshot hoặc rule xử lý mutations phù hợp.

## 29. Property cho composite keys

Với encoding `tenantId#entityId`, một phương pháp nối trực tiếp có thể bị ambiguity:

~~~text
tenant="a#b", entity="c"
tenant="a", entity="b#c"
```

Nếu cả hai tạo `a#b#c`, uniqueness bị phá.

Property:

\[
decode(encode(t,e))=(t,e)
\]

với mọi cặp hợp lệ, kể cả ký tự phân cách/Unicode. Giải bằng **length-prefix, escaping chuẩn hoặc structured key encoding**, không dựa vào “chưa ai nhập ký tự #”.

## 30. Property cho idempotency

Một command `CreatePayment(operationId=K, amount=100)` theo contract idempotent:

~~~text
apply(K)
apply(K)
apply(K)
```

phải có **một business effect** và consistent response/status cho cùng K khi request payload trùng theo policy.

Nhưng:

- Requests cùng K khác payload có thể cần `CONFLICT`.
- Key scope thường theo tenant/operation type.
- Retention của idempotency record phải rõ.
- “Once” áp cho business effect, không nhất thiết một DB/network attempt.
- Timeout có thể để unknown outcome cần query/reconcile.

Không kiểm bằng cách nhìn số lần controller method được gọi; hãy kiểm authoritative ledger/effect count.

## 31. Property cho conditional update

Với document version \(v\):

~~~text
update(expected=v) -> may succeed once
update(expected=v) after successful update to v+1 -> conflict
```

Đây là property cho **CAS** trong cùng document/aggregate với atomic update được cam kết.

Thêm cases:

- Wrong tenant.
- Missing entity.
- Repeated stale version.
- No-op update có tăng version không (theo contract)?
- Two concurrent commands với cùng expectedVersion.
- Client timeout/unknown response.
- Version overflow/generation reset.

Một reference model phải lưu **current version** độc lập với fields trong SUT.

## 32. Property cho delete và tombstone

Chuỗi:

~~~text
Create(K, version=1)
Delete(K, version=2)
BackfillUpsert(K, oldVersion=1)
```

không được hồi sinh K nếu thiết kế yêu cầu tombstone chống stale replay.

Property:

\[
V_{\text{target}} \ge V_{\text{lastApplicableMutation}}
\]

với định nghĩa target version bao gồm **deleted state**, không chỉ records đang tồn tại.

Nếu tombstone được GC theo retention, property cần giới hạn replay horizon hoặc generation/epoch để không đặt giả định không thể đáp ứng.

## 33. Property cho TTL/expiry

Một cache/session contract có thể yêu cầu:

~~~text
if trustedNow >= expiresAt:
  authorization must reject access
```

Ngay cả khi MongoDB TTL monitor/DynamoDB TTL cleanup chưa xóa physical record.

Trường hợp kiểm:

- Exactly at expiry.
- One millisecond/second before/after.
- Timezone parsing.
- Epoch seconds vs milliseconds.
- Clock offset/leeway nếu policy cho phép.
- Rename/copy record không reset expiry trái contract.
- Expired-but-present database item.

Không kiểm “document bị xóa đúng giây 0” đối với engine có asynchronous TTL cleanup.

## 34. Property cho query isolation

Trong multi-tenant NoSQL:

~~~text
For all T1 != T2 and keys K:
  operations authorized for T1
  cannot read/modify records belonging to T2.
```

Sinh cố ý:

- Same entity ID trong hai tenants.
- Tenant IDs có prefix.
- Composite key separator.
- Empty/null tenant.
- Query filter thiếu tenant.
- Pagination cursor của tenant khác.
- Search index results từ nhiều tenants.
- Cache key collision.
- Bulk update/delete filter thiếu tenant predicate.

**Tenant isolation là security invariant**, không chỉ property chức năng.

## 35. Property cho counters

Với counter kiểu cộng:

\[
value_{final}=value_{initial}+\sum_{i\in AppliedUniqueOps}\Delta_i
\]

Phải xác định:

- `AppliedUniqueOps`: business operations nào đã commit đúng một lần?
- Có retries không?
- Counter native NoSQL có idempotency theo API không?
- Có overflow/negative values không?
- Có concurrent adds và stale reads không?
- Có reset/generation không?

Một blind `increment` retry có thể tăng hai lần nếu lần đầu commit rồi response mất. PBT phải test **duplicate attempts** và phân biệt native counter với version-guarded ledger-based updates.

## 36. Property cho merge của CRDT/commutative state

Nếu chọn một merge operation \(M\) cho trạng thái dạng semilattice/CRDT phù hợp, có thể yêu cầu:

**Commutativity**

\[
M(a,b)=M(b,a)
\]

**Associativity**

\[
M(M(a,b),c)=M(a,M(b,c))
\]

**Idempotence**

\[
M(a,a)=a
\]

Những quy luật này giúp state-based CRDT merge **hội tụ khi nhận duplicates/out-of-order** theo assumptions. Không tự áp cho những phép như subtraction hoặc last-timestamp-wins khi domain cần bảo toàn số lượng.

## 37. Property cho event sourcing

Nếu model có event reducer:

~~~text
fold(initialState, events) -> state
```

có thể kiểm:

- Event sequence đầy đủ tạo state hợp lệ.
- Replay cùng history không tự phát external side effects.
- Serialization/upcasting không đổi semantic effect.
- Snapshots + replay tail tương đương full replay.
- Version gaps được phát hiện.
- Duplicate event ID được xử lý theo contract.
- Event-time không bị nhầm source ordering.

Một replay của delta events **không nhất thiết** idempotent nếu reducer cộng trực tiếp; cần inbox/sequence guards hoặc replay từ baseline có thể reset an toàn.

## 38. Property cho snapshot + CDC rebuild

Giả sử source có snapshot state tại boundary \(B\), và một change stream đầy đủ các mutations sau \(B\).

Property:

\[
apply(snapshot_B,changes_{>B})=state_{authoritative\ at\ W}
\]

tại watermark \(W\), **nếu**:

- Snapshot và stream không có gap.
- Events replay đúng source ordering/scope.
- Delete/tombstones được giữ.
- Transformer deterministic.
- SUT áp full-state/patch/delta đúng semantics.
- Không có writes ngoài modeled authority.
- Các versions/generations được so đúng.

Đây là một model-based property hiệu quả cho migration/backfill, nhưng khó nhất là **chứng minh preconditions** của snapshot boundary.

## 39. Property cho read model eventual consistency

Một projection từ source → CDC → target không nên bị buộc đồng bộ tức thì.

Test có thể:

1. Tạo chuỗi mutations có source versions.
2. Gửi events với duplicates và deliberate reorder trong những giới hạn được phép.
3. Sau đó **dừng writes và fault injection**, để pipeline đủ thời gian/fairness phục hồi.
4. Chờ target watermark bắt kịp source watermark theo bounded test policy.
5. So target normalized state với reference model.
6. Kiểm không resurrect delete.
7. Nếu timeout, báo diagnostics, không tự sửa state.

“Eventually” là một property có **giả định tiến triển**. Test finite timeout chỉ tạo bằng chứng thực nghiệm trong budget, không chứng minh hội tụ cho mọi lịch thực thi.

## 40. Property cho index và query

Một index phải trả results nhất quán với source dữ liệu theo consistency/freshness contract.

Ví dụ trong môi trường quiescent:

~~~text
IndexedQuery(status=PAID)
  == FilterFullReferenceModel(status=PAID)
```

Cần kiểm:

- Filter semantics.
- Sort and tie-break order.
- Null/missing.
- Unicode/tokenization/collation.
- Pagination.
- Updates làm bỏ old index entries.
- Deletes.
- Tenant scoping.
- Schema evolution.
- Index rebuild/cutover.

Search engines có refresh visibility delay; test chờ **watermark hoặc supported refresh barrier**, không ngủ một hằng số không được bảo đảm rồi kết luận sai.

## 41. Property cho dữ liệu encryption

Nếu ứng dụng encrypt field với AEAD:

- Decrypt(encrypt(plaintext,AAD),AAD) == plaintext.
- Sửa ciphertext/tag/AAD bị reject.
- Tenant/entity AAD khác không decrypt thành công.
- Key mismatch thất bại.
- Rotation/re-encrypt giữ business plaintext.
- Backup restore giữ wrapped DEK/key references.
- Không ghi plaintext vào storage/logs theo policy.

**Không dùng PBT để tự chứng minh thuật toán AES-GCM an toàn về mật mã**. Kiểm ở đây là cách dùng library và data lifecycle của hệ.

## 42. Property cho schema migration

Một migrator v1→v2 có thể cần:

~~~text
ValidV1 -> ValidV2
LegacyFields preserved/transformed by rule
Repeated migration is idempotent or explicitly rejected
No tenant/key identity changes
Business value unchanged by representation change
```

Không tự yêu cầu “migrate(migrate(x)) == migrate(x)” nếu hàm chỉ chấp nhận v1 và v2 thuộc schema khác; có thể thay bằng một **migration dispatcher** idempotent trên union format, hoặc property “migration lần hai báo ALREADY_MIGRATED”.

## 43. Property về uniqueness

Khi business cần email unique trong từng tenant:

~~~text
Within one tenant:
  at most one authoritative active user
  has a given canonical email.
```

Hai concurrent creates với cùng canonical email phải không cùng commit theo source atomicity/unique index/transaction contract. Test cần sinh **collisions cố ý**, không chỉ random emails.

Cẩn thận: NoSQL stores không phải mọi engine đều có cross-partition uniqueness. Nếu cần invariant này, schema/coordination phải bảo vệ đúng scope.

## 44. Property về order-state machine

Một business state graph:

~~~mermaid
stateDiagram-v2
  [*] --> CREATED
  CREATED --> CONFIRMED
  CREATED --> CANCELLED
  CONFIRMED --> PAID
  CONFIRMED --> CANCELLED
  PAID --> REFUNDED
  CANCELLED --> [*]
  REFUNDED --> [*]
~~~

Các transitions chỉ hợp lệ nếu preconditions/authorization thỏa. Một model có thể sinh:

~~~text
Create
Confirm
Pay
Cancel
Refund
Confirm
Pay
```

và kỳ vọng invalid transitions **không làm state thay đổi**. Nên cân nhắc những business exceptions như chargeback/manual correction và model versioning.

## 45. Property cho transaction atomicity

Nếu một operation phải thay đổi hai records atomically:

~~~text
transfer(A,B,amount):
  debit(A)
  credit(B)
```

Property:

\[
balance_A+balance_B=\text{constant}
\]

ở mỗi **điểm quan sát được theo transactional contract** khi không có fees hoặc external mutations.

Nếu transaction failure, không được thấy trạng thái partial commit theo isolation guarantee. Nếu hệ chỉ eventual atomicity qua saga, property cần là **eventual compensation/ledger conservation** với state trung gian được cho phép, không giả mạo một ACID transaction không tồn tại.

## 46. Property cho optimistic concurrency

Một field `version` được cập nhật:

~~~text
read version=v
write(expectedVersion=v,newState)
```

Hai concurrent writes cùng `v` theo source atomicity nên nhiều nhất một thành công.

Cần kiểm:

- Successful write increments version đúng.
- Failed stale write không đổi value/version.
- Retry sau unknown commit không tạo double effect.
- `version` không reset sau delete/recreate nếu ID generation cần phân biệt.
- Tránh ABA (state A→B→A nhưng version đổi).
- Reads/expectedVersion lấy từ đúng consistency mode.

## 47. Những property không thể dùng với eventual read ngay lập tức

Tránh:

~~~text
write acknowledged -> every get() across all replicas returns latest immediately
```

trừ khi API và consistency mode bảo đảm điều này.

Thay vào đó, chia rõ:

- **Safety của authoritative write**: không có oversell, stale version không commit.
- **Read-your-writes**: chỉ nếu session/consistency API cam kết.
- **Monotonic reads**: chỉ khi sử dụng session/token/route phù hợp.
- **Eventual convergence**: trong điều kiện đủ availability/fairness và khi source quiesces.
- **Bounded staleness**: cần bound cụ thể của hệ.
- **Linearizability**: chỉ khi read/write path có bảo đảm đủ mạnh.

Model thường có thể giữ authoritative state và một **set of allowed observed states** cho reads yếu, thay vì so `read == latest` mọi lúc.

## 48. Kiểm consistency bằng lịch sử operation

Một concurrent history có thể ghi:

~~~text
opId=1  Invoke Write(x=1) at t1
opId=2  Invoke Read(x)    at t2
opId=1  Return success   at t3
opId=2  Return x=0       at t4
```

Khi `Write` và `Read` overlap (read được gọi trước write trả response), một linearizable register có thể cho phép read thấy old value hoặc new value tùy linearization points.

Trái lại:

~~~text
opId=1  Write(x=1) returns success at t1
opId=2  Read(x) invoked at t2>t1, returns x=0
```

có thể vi phạm linearizability **nếu read/write sử dụng cùng logical object, successful write là durable/committed theo contract và không có concurrent overwrite**. Với eventual read, kết quả cũ có thể được phép.

## 49. Linearizability, sequential consistency và serializability

Ba thuật ngữ không được dùng thay nhau:

- **Linearizability:** mỗi operation dường như xảy ra tức thời tại một điểm nằm giữa invocation và response; phải tôn trọng **real-time order** của operations **không overlap**.
- **Sequential consistency:** operations có thể được sắp thành một chuỗi tương thích thứ tự chương trình từng client, không nhất thiết tôn trọng toàn bộ real-time order giữa clients.
- **Serializability:** các transactions tương đương một lịch thực thi tuần tự nào đó; **không tự** đòi real-time order như strict serializability.

Một engine có thể cung cấp single-document atomicity nhưng không cung cấp global linearizable reads cho mọi queries. Chọn **checker theo scope object/transaction và API guarantee**, không kết luận toàn cluster từ một key đơn.

## 50. Khi nào cần linearizability checker?

Dùng khi cần đánh giá:

- Atomic register (get/set) qua failover.
- Conditional write/CAS với quorums đúng policy.
- Distributed lock/lease authority.
- Leader change và stale writes.
- Một key state machine với strong consistency.
- Một số transactions nếu contract đủ mạnh.

Không áp checker tuyến tính hóa lên **eventually consistent query** rồi gọi kết quả fail là database bug. Với weakest consistency, cần một **allowed-observations oracle** khác.

## 51. Lịch sử phải ghi invocation và completion

Một history có các sự kiện:

~~~json
{"opId":"A1","client":"A","type":"invoke","op":"put","key":"k","value":1,"atNanos":100}
{"opId":"B1","client":"B","type":"invoke","op":"get","key":"k","atNanos":120}
{"opId":"A1","client":"A","type":"ok","atNanos":150}
{"opId":"B1","client":"B","type":"ok","result":1,"atNanos":160}
~~~

Mốc `atNanos` ở đây **chỉ có thể so trực tiếp** nếu logger dùng một monotonic clock chung trong cùng runtime hoặc một tracer/scheduler cho thứ tự được bảo đảm; không so tùy tiện `System.nanoTime()` từ hai hosts.

Với nhiều hosts, có thể thu history tại một **client coordinator** gắn invocation/completion events theo protocol, hoặc dùng causal/ordering metadata và uncertainty rõ.

## 52. In-flight và unknown operations

Một write:

~~~text
invoke put(k,1)
network partition
client timeout
```

không có `success` hoặc `definite failure`. Nó có thể đã commit hoặc chưa.

History checker phải giữ operation như **pending/indeterminate** theo mô hình thay vì tự gán `failed` và loại bỏ ảnh hưởng. Một linearization có thể cần xem nó **có hoặc không có effect** trong những lịch tương ứng.

Dedupe/idempotency và **read-after-timeout reconciliation** là cách giúp ứng dụng quyết định retry an toàn.

## 53. Mô hình atomic register

State một key:

~~~text
value = 0

Write(x):
  value := x
  returns ACK

Read():
  returns value
~~~

Với linearizability, một concurrent history chỉ hợp lệ nếu có thể sắp các operations thành một thứ tự tuần tự thỏa:

1. Mỗi operation tương ứng một model transition.
2. Response phù hợp transition.
3. Nếu A hoàn tất trước B bắt đầu thì A phải xếp trước B.
4. Thứ tự trong mỗi client được tôn trọng.

Đây là cách tìm **counterexample cho register**. Nếu test với multi-key transactions, model phải mô tả thêm các keys/transaction boundaries.

## 54. Hai writes chồng thời gian

~~~text
A: put(x=1) invoke --------- return
B:       put(x=2) invoke ------ return
```

Hai writes overlap nên linearizability có thể cho thứ tự A→B hoặc B→A tùy execution; riêng timestamp invocation không đủ quyết định final value.

Khi thêm một read **được gọi sau khi cả hai writes đã trả success**, read phải thấy final value của một thứ tự tuyến tính hợp lệ, trừ khi có write thứ ba hoặc consistency mode không hứa linearizability.

## 55. Kiểm một history bằng tìm kiếm state

Một checker nhỏ có thể dùng backtracking:

~~~text
candidate = operations with completed outcomes
for each eligible operation whose real-time predecessors
    have already been ordered:
  try applying operation to reference model
  if model output matches recorded output:
    recurse
success if all completed operations can be placed
```

Vấn đề:

- Search space có thể tăng theo factorial trong histories nhiều operations.
- Need memoization/pruning.
- Pending writes cần xử lý logic riêng.
- State fingerprint cần chuẩn.
- Multi-key compose assumptions khó.
- Real-time ordering phải được ghi đúng.

Với test cluster thực tế, nên dùng **checker được đánh giá rộng rãi** hoặc công cụ/thuật toán tương ứng, không tin một backtracking demo tự viết cho production safety proof.

## 56. Jepsen, Knossos và công cụ lịch sử

Một hướng phổ biến trong kiểm thử phân tán là kiểu **Jepsen**: chạy workload concurrent, inject faults, ghi invocation/completion history và kiểm consistency theo model/checker như Knossos/Elle tùy property cần kiểm.

Các thành phần mang tính phương pháp:

- **Client workload generator** phát operations có IDs.
- **Nemesis/fault injector** tạo partitions, process restart, clock skew hoặc node failure.
- **History recorder** có operation outcomes.
- **Checker** tìm violations theo consistency contract.
- **Shrinker/minimizer** và report evidence.
- **Recovery phase** để xem liveness/convergence.
- **Independent model** cho state machine.

Không phải mọi loại history đều kiểm được bằng cùng một checker; ví dụ cycles trong transactional dependency graph khác register linearizability.

## 57. Jepsen-style testing không thay production monitoring

Một run với 5 nodes, 1 phút và không tìm thấy failure chỉ nói rằng **không phát hiện phản ví dụ trong phạm vi đã thử**.

Không chứng minh:

- Mọi network partitions.
- Mọi storage stalls.
- Mọi workload distributions.
- Mọi version/topology.
- Mọi background compactions.
- Không có security bug.
- Thỏa liveness vô thời hạn.

Hãy coi đây là **evidence bổ sung** cho formal reasoning, integration tests, production SLO monitoring và incident replay.

## 58. Transaction history checker cần dữ liệu nào?

Với một transaction đọc/ghi nhiều keys:

~~~text
txn T1:
  read A=100
  write A=80
  write B=120
```

History nên ghi:

- Invocation/completion của transaction.
- Reads được quan sát trong transaction.
- Writes được đề nghị.
- Commit/abort/unknown status.
- Conflict/timeout outcomes.
- Key/version/transaction ID.
- Read/write concern hoặc isolation mode.
- Fault/topology events.

Một test chỉ ghi `transaction committed=true` nhưng không ghi reads/versions có thể thiếu thông tin để dựng dependency graph.

## 59. Serializability checker không chỉ so final state

Hai histories có thể có cùng final balances nhưng một có **write skew** vi phạm invariant được giả định trong transaction isolation.

Ví dụ hai on-call doctors:

~~~text
Initially A_oncall=true, B_oncall=true
Transaction T1 reads both true, sets A=false
Transaction T2 reads both true, sets B=false
Final state: both false
```

Nếu domain yêu cầu luôn ít nhất một on-call, snapshot isolation có thể cho anomaly kiểu write skew trong những conditions phù hợp. Một checker cần xem **read dependencies** và transaction semantics, không chỉ final count.

Đối với NoSQL, transaction isolation là tùy engine/version/config; không mặc định mọi multi-document transaction bảo đảm serializability.

## 60. Causal consistency có oracle riêng

Nếu hệ hứa causal consistency, test có thể tạo:

~~~text
Client A writes x=1.
Client A reads own write or propagates session token.
Client B starts with causal context from A.
Client B reads x.
```

Mục tiêu là B không quan sát một state **trái causal dependency** theo protocol.

Không thể ép một client khác **không mang causal context** phải thấy x=1 ngay khi hệ chỉ hứa session/causal guarantees. Need đúng session tokens, cluster times và read policies.

## 61. Eventual convergence test: có nên dùng sleep?

Một test:

~~~java
Thread.sleep(1000);
assertEquals(source, target);
~~~

có thể flaky nếu GC pause, CI slow, network jitter hoặc chỉ số refresh dài hơn 1 giây.

Tốt hơn:

~~~text
poll target applied watermark
wait until W_source is applied (bounded deadline)
then compare normalized state
```

Nếu không có watermark, dùng bounded polling với backoff và báo độ trễ thực, nhưng không coi một hằng số sleep là **guaranteed convergence bound** khi service không hứa bound.

## 62. Resource-aware correctness testing

Một property test trực tiếp trên database thật phải cân nhắc:

- Số operations/second.
- Number of collections/tables.
- WCU/RCU/compute costs.
- Connection pools.
- Hot partition traffic.
- CI environments shared.
- Cleanup retention.
- Snapshot/repair overhead.
- Slow/history checker cost.

Một suite test đúng dữ liệu nhưng gây outages môi trường chung là một test harness nguy hiểm. Cần sandbox, bounded concurrency/tries, rate limits và automatic cleanup.

## 63. Không dùng production data tùy ý để random writes

Khi chạy PBT trên database:

- Dùng isolated test namespaces/tables.
- Scoped credentials.
- Unique run IDs.
- Không sử dụng PII thật nếu không được phép.
- TTL cleanup có kiểm soát.
- Delete only owned test resources.
- Rate-limit workload.
- Network fault injection chỉ trong môi trường được phép.
- Không disable authorization để dễ test.
- Không chỉnh clock production.

Một property failing không được để lại hàng triệu test documents chiếm storage và phá SLO.

---

## 64. Java reference model cho một versioned key-value store

Định nghĩa hợp đồng tối giản:

- `put(key,value,expectedVersion)` thành công nếu key tồn tại và version khớp, hoặc có một command `create` riêng.
- Mỗi mutation thành công tăng version.
- Nếu version sai, không thay đổi state.
- Delete tạo tombstone giữ version.
- `get` trả state hoặc tombstone theo contract.

Sử dụng **một model thuần trong Java**:

~~~java
import java.util.HashMap;
import java.util.Map;

final class KeyValueModel {
    record Entry(String value, long version, boolean deleted) {}

    enum Result { APPLIED, CONFLICT, NOT_FOUND }

    private final Map<String, Entry> state = new HashMap<>();

    Result create(String key, String value) {
        if (state.containsKey(key)) {
            return Result.CONFLICT;
        }
        state.put(key, new Entry(value, 1, false));
        return Result.APPLIED;
    }

    Result update(String key, long expectedVersion, String value) {
        Entry old = state.get(key);
        if (old == null || old.deleted()) {
            return Result.NOT_FOUND;
        }
        if (old.version() != expectedVersion) {
            return Result.CONFLICT;
        }
        state.put(key, new Entry(value, old.version() + 1, false));
        return Result.APPLIED;
    }

    Result delete(String key, long expectedVersion) {
        Entry old = state.get(key);
        if (old == null || old.deleted()) {
            return Result.NOT_FOUND;
        }
        if (old.version() != expectedVersion) {
            return Result.CONFLICT;
        }
        state.put(key, new Entry(null, old.version() + 1, true));
        return Result.APPLIED;
    }

    Entry get(String key) {
        return state.get(key);
    }

    Map<String, Entry> snapshot() {
        return Map.copyOf(state);
    }
}
~~~

Đây là Java 17+ vì dùng records. Model giữ tombstone để chặn re-create theo cùng key/generation; nếu business muốn cho re-create, phải định nghĩa generation/epoch hoặc `createAfterDelete` khác. Đây **không phải implementation database production**.

## 65. Vì sao model giữ deleted entry?

Nếu xóa hoàn toàn entry khỏi map:

~~~text
Create K version 1
Delete K version 2
Historical backfill writes K version 1
```

Target trống và có thể nhận lại v1. Tombstone `version=2` giữ thông tin mutation mới nhất.

Trong sản phẩm thật, tombstone retention và replay horizon cần được quản lý. Model cố tình không làm garbage collection để kiểm invariant trong phạm vi test này.

## 66. State model vs adapter SUT

Một interface adapter:

~~~java
interface VersionedStore {
    StoreResult create(String tenant, String key, String value);
    StoreResult update(
        String tenant, String key, long expectedVersion, String value);
    StoreResult delete(
        String tenant, String key, long expectedVersion);
    StoreEntry read(String tenant, String key);
}
~~~

Có thể có các adapter:

- MongoDB với atomic `findOneAndUpdate`/condition.
- DynamoDB với `ConditionExpression`.
- Cassandra với LWT cho semantics phù hợp.
- Redis với Lua script hoặc transactions theo single key.
- In-memory fake để chạy nhanh.

**Không sao chép model sang adapter y hệt rồi coi test là independent oracle**; mục tiêu là thử một SUT triển khai cơ chế riêng so với rules.

## 67. Mô hình stateful test loop

Ý tưởng:

~~~text
model = new KeyValueModel()
sut = createIsolatedNoSqlAdapter()

for op in generatedCommands:
    expected = model.apply(op)
    actual = sut.execute(op)

    compareOutcome(expected, actual)
    compareObservableStateWithinConsistencyContract(model, sut)
```

Điều kiện bắt buộc:

- Model transition phải gắn với **actual confirmed SUT outcome** nếu operation ambiguous.
- Khi SUT timeout sau potential commit, không thể tiếp tục update model như một definite failure.
- Reads cần consistency mode đúng.
- Mỗi test run có namespace riêng để không bị external mutation.
- Cleanup trên test-only data.

Một model loop thuần tuần tự **không chứng minh concurrency correctness**.

## 68. Có nên update model trước hay sau SUT?

Với definite deterministic response, có thể tính expected state trong bản copy model trước rồi so với actual.

Nhưng nếu database call trả `UNKNOWN_COMMIT`, model có thể phải giữ **các state có thể có**:

~~~text
State S before operation
Possible next states = {S, apply(S, op)}
```

Sau đó reconcile bằng authorized read/log/operation ID. Nếu tự chọn một state mà không có bằng chứng, subsequent assertions có thể sai.

Đối với eventual reads, model có thể track **authoritative state** và **allowed replica observations** dựa trên consistency contract.

## 69. Mô hình `Create`, `Update`, `Delete`, `Read` thành commands

Một kiểu biểu diễn Java 17+:

~~~java
sealed interface StoreCommand
    permits CreateCmd, UpdateCmd, DeleteCmd, ReadCmd {}

record CreateCmd(String key, String value)
    implements StoreCommand {}

record UpdateCmd(String key, long expected, String value)
    implements StoreCommand {}

record DeleteCmd(String key, long expected)
    implements StoreCommand {}

record ReadCmd(String key)
    implements StoreCommand {}
~~~

Khi chạy, dispatcher:

- Kiểm preconditions theo command contract.
- Áp lên model.
- Gọi adapter NoSQL.
- So outcomes.
- Ghi history details.
- Có thể thu current state sau xác nhận khi consistency cho phép.

Cố ý chọn ít keys/versions để sinh **collisions và stale writes**.

## 70. jqwik generator cho chuỗi commands

Ví dụ:

~~~java
import net.jqwik.api.*;
import java.util.List;

class CommandGenerators {
    @Provide
    Arbitrary<List<StoreCommand>> histories() {
        Arbitrary<String> keys =
            Arbitraries.of("k1", "k2", "k3");

        Arbitrary<String> values =
            Arbitraries.of("", "v1", "v2", "đ");

        Arbitrary<Long> versions =
            Arbitraries.longs().between(0, 5);

        Arbitrary<StoreCommand> creates =
            Combinators.combine(keys, values)
                .as((k, v) -> (StoreCommand) new CreateCmd(k, v));

        Arbitrary<StoreCommand> updates =
            Combinators.combine(keys, versions, values)
                .as((k, v, x) ->
                    (StoreCommand) new UpdateCmd(k, v, x));

        Arbitrary<StoreCommand> deletes =
            Combinators.combine(keys, versions)
                .as((k, v) ->
                    (StoreCommand) new DeleteCmd(k, v));

        Arbitrary<StoreCommand> reads =
            keys.map(k -> (StoreCommand) new ReadCmd(k));

        return Arbitraries.oneOf(
                creates, updates, deletes, reads
            )
            .list()
            .ofMinSize(1)
            .ofMaxSize(80);
    }
}
~~~

`StoreCommand`, records phải được khai báo như phần trước. `@Provide` có thể được đưa vào chính property class hoặc dùng `@ForAll("histories")` theo scope jqwik tương ứng. Generator sinh nhiều invalid/stale commands có chủ đích; suite phải biết expected outcomes thay vì tự assume valid.

## 71. jqwik: thử model với adapter

Khung test ý tưởng:

~~~java
import net.jqwik.api.*;
import java.util.List;

class StoreModelProperties extends CommandGenerators {
    @Property(tries = 200)
    void commandsMatchModel(
            @ForAll("histories") List<StoreCommand> commands) {

        KeyValueModel model = new KeyValueModel();

        try (VersionedStoreAdapter sut =
                createFreshIsolatedTestAdapter()) {

            for (StoreCommand command : commands) {
                ExpectedTransition expected =
                    ModelRunner.evaluateAndAdvance(model, command);

                ActualTransition actual =
                    SutRunner.execute(sut, command);

                Assertions.assertEquivalent(expected, actual);

                Assertions.assertObservableState(
                    model, sut, ConsistencyMode.STRONG_READ);
            }
        }
    }
}
~~~

**Đây là pseudocode Java**: `VersionedStoreAdapter`, runners, assertions và consistency enum chưa được định nghĩa. Nó minh họa cấu trúc model-vs-SUT, không phải unit test có thể copy chạy nguyên xi. Trong implementation thật, phải xử lý unknown outcomes và check read mode đúng; chẳng hạn không thể tự yêu cầu `STRONG_READ` nếu adapter target không hỗ trợ.

## 72. Dùng `@Property` cho stateful tests có hiệu quả ra sao?

Mỗi lần jqwik gọi property:

1. Tạo một `commands` list mới.
2. Tạo model ở initial state.
3. Tạo SUT ở **namespace sạch**.
4. Apply từng command.
5. So outcome/property sau mỗi bước hoặc cuối sequence.
6. Nếu fail, jqwik shrink list và parameters.
7. Ghi seed/shrunk trace.
8. Cleanup SUT; rerun deterministic counterexample.

Hệ thật có startup/network overhead; có thể chạy model nhanh với hàng nghìn sequences, còn database integration tests chạy ít hơn nhưng sâu hơn.

## 73. Test fixture isolation và parallel execution

Khi jqwik chạy nhiều tries/threads, dùng chung collection có thể gây interference:

~~~text
Try A creates key k1
Try B deletes key k1
Try A reads k1 -> missing
```

Model A không biết lệnh của B và test thất bại giả.

Cách ly:

- Unique namespace/table/database per test run.
- Tenant/run ID prefix có verified isolation.
- Transaction rollback khi engine hỗ trợ và phù hợp.
- Serialized execution cho một resource không thể cách ly.
- Cleanup bằng exact test prefix, không wildcard nguy hiểm.
- Test credentials chỉ được sửa test resources.

Nếu cần concurrency **trong cùng test**, cố ý chia nhiều clients trong **một namespace thử nghiệm**, khác parallel interference giữa hai tests độc lập.

## 74. Shrinking và side effects trên SUT

Một shrinker có thể chạy lại counterexample hàng chục/hàng trăm lần. Nếu mỗi lần gọi external production service hoặc gửi email thật, hệ sẽ chịu side effects nguy hiểm.

Cần:

- Isolated DB/test doubles.
- Reset state giữa shrink attempts.
- Idempotent fixtures.
- Rate/cost cap.
- Disable real notifications/payment.
- Seeded deterministic mocks.
- Cleanup và resource budget.

**Càng test tự động nhiều thì môi trường kiểm thử càng phải có safety boundary mạnh.**

## 75. Model vs SUT: đừng kiểm kết quả mơ hồ như bằng nhau tuyệt đối

Một SUT MongoDB có thể trả server-generated `_id`, `clusterTime` hoặc audit timestamp, trong khi model chỉ quản lý business state.

So:

~~~text
normalize(observedSutRecord) == modelBusinessState
```

Trong normalize:

- Bỏ/kiểm riêng system metadata.
- Canonicalize numeric types.
- Không bỏ fields ảnh hưởng domain.
- Giữ tenant/key/version.
- So semantics của null/missing.
- Dùng stable ordering cho lists nếu order không quan trọng.
- Không ignore deletes chỉ vì target không trả tombstones qua API đọc công khai.

Một normalizer quá rộng có thể che data-loss bug.

## 76. Negative tests: invalid commands không đổi state

Property:

~~~text
For every invalid operation rejected with definite failure:
  authoritative state remains unchanged.
```

Ví dụ:

- Negative stock reservation.
- Wrong tenant.
- Stale `expectedVersion`.
- Duplicate unique key.
- Invalid transition.
- Unauthorized bulk delete.
- Invalid decimal.
- Malformed encrypted envelope.

Ngoại lệ: API có thể ghi audit record/rejection counter dù business object không đổi; phân biệt **business state** với **observability side effects**.

## 77. Invalid command precondition và real database errors

Không nhầm:

- `CONFLICT`: expected business rejection.
- `VALIDATION_FAILED`: deterministic input rejection.
- `UNAUTHORIZED`: access rejection.
- `THROTTLED`: capacity/availability issue.
- `TIMEOUT`: ambiguous operation outcome.
- `INTERNAL_ERROR`: có thể là implementation fault.

Một test suite báo mỗi `CONFLICT` là failure sẽ tạo nhiều false positives; một suite swallow mọi exception sẽ bỏ qua lỗi thật.

## 78. State-machine transition coverage

Thay vì chỉ đếm commands, đo transitions:

~~~text
ABSENT -> CREATED
CREATED -> UPDATED
UPDATED -> UPDATED
CREATED -> DELETED
DELETED -> RECREATE_ATTEMPT
DELETED -> READ
STALE_UPDATE -> REJECTED
DUPLICATE_CREATE -> REJECTED
~~~

Nếu generator không bao giờ tạo `DELETED -> RECREATE_ATTEMPT`, model không kiểm chính sách tombstone/generation.

Có thể bias generator dựa vào current model state để tăng xác suất transitions hiếm, đồng thời vẫn sinh invalid operations có chủ đích.

## 79. Một generator thích nghi theo model state

Một `CommandGenerator` có thể:

~~~text
if model empty:
  more creates, some invalid reads

if model has records:
  pick existing key frequently
  pick old version sometimes
  issue duplicate create sometimes
  occasionally delete
  sometimes use another tenant
```

Lợi ích: không lãng phí 90% tries vào `NOT_FOUND` khi muốn test update transitions. Nhưng generator phải **không tự xóa invalid outcomes hoàn toàn**.

Một số model frameworks hỗ trợ rules/preconditions; cũng có thể tự viết generator điều khiển bởi model và áp shrinker phù hợp.

## 80. Regression test từ shrunk counterexample

Một lỗi tìm được:

~~~text
create(k, version=1)
delete(k, version=2)
retry historical upsert(k, version=1)
observed: k revived
```

Sau khi sửa, nên giữ:

- One deterministic example regression.
- Original PBT property.
- Seed/schedule/test config.
- Minimal history.
- Root-cause note.

Không chỉ fix code rồi xóa seed; một regression nhỏ giúp bảo vệ đúng lỗi trong future changes và CI nhanh hơn.

---

## 81. Concurrent commands: không phải `parallelStream` ngẫu nhiên là đủ

Một test:

~~~java
commands.parallelStream().forEach(sut::execute);
~~~

có concurrency nhưng:

- Interleavings ít kiểm soát.
- Không chắc hai writes thực sự overlap tại điểm race.
- Thread pool/scheduler không deterministic.
- Không có invocation/completion history chính xác.
- Có thể làm DB quá tải thay vì tạo race cần kiểm.
- Shrinking khó giữ concurrency schedule.

Dùng **barriers, latches, controlled schedulers, fault hooks và operation history recorder** để tạo kịch bản có mục tiêu, ngoài fuzzing ngẫu nhiên.

## 82. Java: test hai CAS writers với cùng version

Ví dụ skeleton dùng JUnit-style assertions và `CountDownLatch`:

~~~java
import java.util.concurrent.*;
import static org.junit.jupiter.api.Assertions.*;

void concurrentCasSingleWinner(VersionedStore sut)
        throws Exception {

    sut.create("tenant-A", "k1", "initial");

    CountDownLatch ready = new CountDownLatch(2);
    CountDownLatch go = new CountDownLatch(1);

    ExecutorService pool = Executors.newFixedThreadPool(2);
    try {
        Callable<StoreResult> writerA = () -> {
            ready.countDown();
            go.await();
            return sut.update("tenant-A", "k1", 1, "A");
        };

        Callable<StoreResult> writerB = () -> {
            ready.countDown();
            go.await();
            return sut.update("tenant-A", "k1", 1, "B");
        };

        Future<StoreResult> a = pool.submit(writerA);
        Future<StoreResult> b = pool.submit(writerB);

        assertTrue(ready.await(5, TimeUnit.SECONDS));
        go.countDown();

        StoreResult ra = a.get(10, TimeUnit.SECONDS);
        StoreResult rb = b.get(10, TimeUnit.SECONDS);

        long successes =
            java.util.stream.Stream.of(ra, rb)
                .filter(r -> r == StoreResult.APPLIED)
                .count();

        assertEquals(1, successes);
        assertEquals(2, sut.read("tenant-A", "k1").version());
    } finally {
        go.countDown();
        pool.shutdownNow();
    }
}
~~~

Ví dụ phụ thuộc các domain interfaces/types đã nêu. Chỉ hợp lệ khi adapter có **atomic per-key CAS** và test không gặp ambiguous timeouts; nếu timeout/unknown, phải reconcile trước khi kết luận số winners. `ready` barrier tạo overlap ở client, nhưng không ép hai operations chạm database đúng cùng microsecond.

## 83. Không tự động gọi concurrent CAS test là linearizability proof

Hai writers cùng version và chỉ một thắng là evidence cho atomic CAS ở một key dưới lịch đã thử.

Chưa kiểm:

- Reads giữa writes.
- Failover/partition.
- Stale replicas.
- Unknown commits.
- Multi-key transactions.
- All possible interleavings.
- Storage crashes after ACK.
- Cross-region concurrent writers.

Một **history checker** với faults/multiple clients bổ sung độ sâu. Kết quả pass có scope hữu hạn.

## 84. Controlled pause để tạo race

Một test hook (chỉ trong environment thử nghiệm) có thể:

~~~text
A reads target version 1
PAUSE A before conditional update
B updates to version 2
RESUME A
A attempts update(expected=1)
Expected: A rejected with conflict
```

Đây là kịch bản deterministic mạnh cho stale write. Nếu test cần thay `Thread.sleep` bằng synchronisation hooks, phải đảm bảo các hooks không xuất hiện ở production hoặc bị bật trái phép.

## 85. Fault injection matrix

| Fault | Property cần quan sát |
|---|---|
| Client request timeout | Không double apply khi retry |
| Server ACK lost after commit | Unknown outcome reconciled |
| Process killed after write | Checkpoint không skip work |
| Replica offline | Read/write behavior đúng consistency mode |
| Network partition | Không tạo two authoritative writers |
| Leader failover | Source term/version không lùi |
| GC pause > lease | Stale worker không commit trái quyền |
| Retry duplicate event | Sink idempotent |
| CDC order shuffle | Full-state version/sequence rule đúng |
| TTL expired-but-present | Auth/expiry policy vẫn đúng |
| Compaction/index build | Correctness vẫn giữ, liveness trong budget |
| Restore old snapshot | Generation/fencing metadata được xử lý |
| Clock skew | Không dùng client time làm order invariant |
| KMS decrypt unavailable | Không fail-open plaintext |
| Poison record | Quarantine, không đánh dấu complete sai |

Fault injection nên được chọn theo **failure model và risk**; không phá mạng/clock của production hệ chung.

## 86. Unknown commit trong reference model

Ví dụ:

~~~text
Client A sends reserve(K, 1)
Database commits
Response is lost
Client sees timeout
Client retries
```

Model ban đầu có thể có hai khả năng sau timeout:

~~~text
S0: stock unchanged
S1: stock decremented once
```

Sau retry với **same idempotency key**, expected business effect vẫn tối đa một lần. Sau reconcile, model có thể thu hẹp tập trạng thái có thể.

Không có idempotency/ledger và không thể query outcome, test phải đánh giá đó là **design gap**, không tùy chọn một kết quả để ép assertion pass.

## 87. Fault model phải cụ thể

Một test “network partition” cần nêu:

- Client ↔ primary hay primary ↔ replica?
- Partition symmetric hay asymmetric?
- Có quorum không?
- Node nào có thể vẫn đọc/ghi?
- Server/driver retry policy?
- Lost/delayed/reordered packets?
- Lease authority có reachable không?
- Key value nào được coi source of truth?
- Mốc nào restore connectivity?

Nếu một tool chỉ kill node hoàn toàn, nó có thể không tái hiện **zombie worker vẫn gửi write** trong partial partition.

## 88. Clock và timestamps trong PBT

Generator thời gian nên tạo:

- Same timestamp cho nhiều writes.
- Timestamps đi lùi.
- Clock offset ± seconds.
- Midnight/timezone boundaries.
- Epoch seconds/milliseconds mismatch.
- Expiry exactly at boundary.
- Future timestamps.
- Out-of-order event-time vs processing-time.

Nhưng hãy dùng timestamp theo đúng role:

- Wall time cho audit/expiry.
- Source version/log position cho authoritative state order.
- Monotonic elapsed cho timeout cục bộ.
- HLC/causal metadata theo protocol đã cam kết.

Không mặc định mọi engine conflict resolution chọn `Instant.now` của Java.

## 89. Retry storm cũng có thể che correctness bug

Một worker bị throttled, SDK retry tự động và application retry thêm tạo rất nhiều attempts. Một mutation idempotent có thể vẫn đúng nhưng làm dịch vụ mất SLO.

Mở rộng property hệ thống:

~~~text
For a bounded request workload and configured retry policy:
  attempts per logical operation <= configured budget
```

và một performance/resource guardrail:

~~~text
Under defined failure scenario:
  no unbounded work queue/memory growth
```

Đây là **non-functional property** gắn với test model, không chỉ equality của dữ liệu.

## 90. Shrinking concurrent histories

Nếu history 1000 operations chứa violation, một minimizer có thể:

- Giữ 2–5 conflicting operations.
- Giảm keys/tenants.
- Bỏ background reads không ảnh hưởng.
- Giữ real-time precedence constraints.
- Chỉ giữ faults cần để trigger.
- Re-run lịch để xem failure vẫn tồn tại.

Khó khăn: concurrency non-deterministic và unknown responses. Một shrunk history cần **vẫn là lịch khả thi** theo model; không tạo một “phản ví dụ” không bao giờ xảy ra được.

## 91. Linearizability checker có thể không tìm thấy lỗi vì history thiếu thông tin

Một failure khi collector chỉ ghi:

~~~text
write success
read old
```

nhưng không có thời điểm invocation/completion, không biết operations overlap hay không, nên không kết luận linearizability violation chắc chắn.

Cần ghi:

- Operation IDs.
- Client identifiers.
- Invocation/completion order.
- Input/output.
- Timeout/unknown categories.
- Source key/generation.
- Read/write consistency settings.
- Faults/topology.
- Accepted state transitions.

**History collection là một phần của correctness test**, không phải log trang trí.

## 92. Cassandra: test theo consistency và timestamps

Các property đáng kiểm:

- Write timestamp conflict resolution theo scope.
- Conditional LWT outcome đúng khi có cạnh tranh.
- Tombstones/delete không bị ghi cũ hồi sinh theo policy.
- TTL behavior ở boundary/cleanup.
- Replica staleness theo consistency level.
- Per-partition operation ordering.
- Retry/idempotency khi read/write timeout.
- Hot partition/compaction stress không làm mất business invariant.

Cần biết `LOCAL_ONE` khác `LOCAL_QUORUM`, và LWT có protocol riêng. Không dùng một checker linearizable cho reads ở consistency mode yếu mà không kiểm requirement.

## 93. Cassandra LWT vs regular write

Một command kiểu:

~~~sql
UPDATE inventory
SET available = 0
WHERE tenant_id = 't1' AND sku = 'S1'
IF available = 1;
~~~

khi dùng conditional update có semantics của LWT theo engine version/config, khác một ordinary timestamp LWW write.

Trong test:

- Đọc outcome applied/not-applied.
- Kiểm cùng primary key/partition.
- Sinh concurrent conditional attempts.
- Kiểm consistency settings và timeouts.
- Không tự retry non-idempotent business operation không kiểm kết quả.

Đoạn CQL chỉ minh họa hướng kiểm, không phải một inventory ledger transaction đầy đủ.

## 94. MongoDB: single-document atomic property

MongoDB cung cấp atomic mutation ở phạm vi một document theo API/transaction semantics. Một property:

~~~text
For all concurrent updates with same expected version,
  at most one advances a given version of that document.
```

Các cases:

- `findOneAndUpdate` with version predicate.
- Duplicate-key on upsert races.
- Retryable writes.
- Primary step-down.
- Read concern/read preference.
- Change Streams replay.
- Multi-document transactions when used.

Không suy từ atomic single-document update sang cross-document serializability tự động.

## 95. MongoDB: Change Stream projection test

Một test end-to-end:

1. Bật change capture phù hợp test deployment.
2. Tạo source document version 1.
3. Update version 2 rồi delete version 3.
4. Inject duplicate event delivery.
5. Pause target consumer; replay old version 1 sau delete.
6. Assert target vẫn có tombstone/version 3 hoặc không hiện record.
7. Reconcile per-source watermark.
8. Kill/restart consumer và resume token theo retention.

Nếu Change Stream token hết hạn, test phải **báo không còn khả năng replay theo protocol**, không reset offset rồi tuyên bố target converge.

## 96. DynamoDB: conditional version property

Với item `(pk,sk)` và `sourceVersion`:

~~~text
incoming v7
target v8
Conditional Put should not overwrite target v8.
```

Bổ sung:

- Concurrent `PutItem`/`UpdateItem` conditions.
- Missing version field.
- TTL expired-but-present.
- `BatchWriteItem` không có condition per item.
- Global Tables/multi-region conflict semantics.
- Strong vs eventually consistent reads.
- SDK retries/unknown commits.
- DynamoDB Streams duplicate/out-of-order across shards.

Không coi `ConditionalCheckFailedException` là server overload; khi model mong conflict, đó là **hành vi đúng**.

## 97. DynamoDB: đọc eventual và strong nhất quán khác nhau

Một property test trên DynamoDB phải phân biệt:

- Conditional write trên base item.
- `GetItem` với chế độ strong read được hỗ trợ.
- Eventual read mặc định của một số đường truy vấn.
- GSI có visibility lag theo semantics của dịch vụ.
- Global Tables có reconciliation/conflict policy riêng.
- Streams có shard ordering và retention.

Không dùng một property `read == latest` áp cho cả strong và eventual modes. Với eventual reads, test có thể chấp nhận trạng thái cũ trong tập allowed observations, rồi kiểm hội tụ sau khi hệ quiescent. Ghi rõ key, path, IAM, consistency flags, retry và source version khi báo failure.

## 98. Redis: test lock khác test business write

Một Redis `SET key token NX PX timeout` có thể cấp quyền tạm theo quy tắc của Redis instance. PBT/state model nên sinh:

~~~text
A acquires token-A.
A pauses past TTL.
B acquires token-B.
A attempts unlock.
A attempts old downstream write.
~~~

Hai bất biến riêng:

1. A không thể xóa lock hiện thuộc B nếu unlock so token atomically.
2. A không được commit business effect trái quyền sau khi B trở thành owner theo giao thức đã chọn.

Điều thứ nhất có thể kiểm với Lua compare-and-delete. Điều thứ hai **không tự được bảo đảm** vì Redis lock value đúng: cần fencing/authority/conditional guard tại sink, cùng failure model cho replication/failover.

## 99. Redis Streams consumer state

Một model cho stream consumer có thể giữ:

~~~text
messageId
payloadVersion
deliveryCount
pending/acknowledged state
businessAppliedOperationIds
lastDurableCheckpoint
```

Sinh duplicate deliveries, consumer crash, reclaim pending, trim/retention, poison message. Properties:

- Không ACK trước durable effect khi contract đòi điều đó.
- Redelivery không thực hiện business effect hai lần.
- Pending records có đường recovery khi consumer chết.
- Checkpoint không nhảy qua records chưa có durable disposition.
- Một stream bị trim mất records chưa áp phải báo gap/recovery failure.

Không đòi broker gửi đúng một lần nếu delivery semantics là at-least-once.

## 100. Search projection: chọn oracle phù hợp

Một model nguồn có 300 products với fields `tenantId,category,status,price,version` có thể trả query expected từ một bộ lọc in-memory.

Sau khi Search projection áp tới watermark phù hợp, kiểm:

- Không thiếu eligible IDs.
- Không trả forbidden tenant IDs.
- Không giữ document đã bị delete.
- Update status/category loại bỏ old index entries.
- Sort có deterministic tie-break.
- Pagination không skip/duplicate trong snapshot semantics.
- Mapping/normalization đúng contract.

Không tự so exact full-text relevance score nếu analyzer/scoring algorithm không thuộc model; có thể kiểm inclusion/term matching trong phạm vi semantics được tài liệu hóa.

## 101. Metamorphic test cho query inclusion

Giả sử cùng một immutable dataset, query \(Q_1\) là `status=PAID`, query \(Q_2\) là `status=PAID AND tenant=T1`.

Khi lấy **full result set** không `topK`:

\[
results(Q_2)\subseteq results(Q_1)
\]

Cần đồng nhất snapshot/visibility point. Nếu có relevance ranking và `LIMIT 10`, tập top ten của \(Q_2\) không nhất thiết nằm trong top ten của \(Q_1\), nên property phải được giới hạn đúng.

## 102. Pagination cursor phải gắn với request scope

Sinh cursor cho tenant A, rồi thử dùng với tenant B:

~~~text
cursorA = list(tenantA).nextCursor
list(tenantB, cursorA)
```

Oracle theo contract có thể yêu cầu reject cursor không tương thích hoặc server ràng buộc nó với trusted tenant/filter context. Sinh:

- Cursor bị sửa bytes.
- Cursor hết hạn.
- Cursor từ schema/sort version cũ.
- Cursor tenant khác.
- Empty page nhưng vẫn có next cursor.
- Insert/delete concurrent.

Đừng dùng cursor opaque không được verify như một quyền truy cập cho dữ liệu khác tenant.

## 103. Composite key collisions

Nếu composite key được nối:

~~~text
tenant + "#" + entityId
```

hai cặp `(tenant="a#b", id="c")` và `(tenant="a", id="b#c")` có thể cùng thành `a#b#c`.

Property:

\[
decode(encode(tenant,id))=(tenant,id)
\]

trên toàn domain hợp lệ. Dùng escaping/length-prefix/structured encoding theo thiết kế. Test cả Unicode, reserved prefix, empty values, keys gần size limit và case normalization.

## 104. Missing field và null khác nhau

Hai documents:

~~~json
{"middleName": null}
~~~

và:

~~~json
{}
~~~

có thể có semantics khác trong validation, index, filter và patch updates. Generator cần:

- Missing.
- Explicit null.
- Empty string/list/map.
- Numeric zero.
- Boolean false.
- Unknown extra field.
- Deprecated field.
- Type mismatches.

Model phải định nghĩa rõ **khi nào normalize chúng như nhau**; không dùng một JSON comparator bỏ null để che bug.

## 105. Numeric precision và serialization

NoSQL systems có integers, decimals, floats và các BSON/JSON types khác nhau. Properties:

- Round-trip giữ giá trị supported.
- Decimal chính xác theo scale.
- Không overflow 32-bit/64-bit âm thầm.
- Tính tiền bằng minor units/BigDecimal theo contract.
- Large IDs không bị mất precision qua JavaScript gateway.
- NaN/Infinity được reject hoặc normalize rõ.
- Time units seconds/milliseconds không trộn.

Tránh `double` cho bất biến ledger đòi exact arithmetic.

## 106. Unicode và locale

Generator nên chứa:

~~~text
"Đà Nẵng"
"đà nẵng"
"e\u0301" (base letter and combining mark)
"é" (precomposed)
"İ"
"ß"
"🙂"
```

Các properties:

- Key normalization deterministic.
- Lookup consistency theo locale policy.
- Không tạo cross-tenant collision.
- Stable pagination order với tie-break.
- Không mất byte/character trong codec.
- Không dựa vào default JVM locale không kiểm soát.

Một `lowercase` đơn giản chưa chắc định nghĩa được semantics cho mọi ngôn ngữ.

## 107. Test TTL bằng virtual time, không đổi clock production

Có thể inject `java.time.Clock` để kiểm boundary:

~~~java
Clock before = Clock.fixed(
    Instant.parse("2026-11-14T08:59:59Z"),
    ZoneOffset.UTC
);

Clock at = Clock.fixed(
    Instant.parse("2026-11-14T09:00:00Z"),
    ZoneOffset.UTC
);
~~~

Kiểm authorization từ chối khi `now >= expiresAt`, kể cả item còn tồn tại trong MongoDB TTL/DynamoDB TTL asynchronous cleanup. Java fake clock không đổi server clock của Redis, MongoDB hoặc DynamoDB; integration test TTL phải tôn trọng engine semantics.

## 108. Test scheduler có thể tạo interleaving mục tiêu

Một deterministic schedule:

~~~text
A reads version 1.
Pause A before update.
B writes version 2.
Resume A.
A writes expectedVersion 1.
Expected: conflict, state remains version 2.
```

Với event consumer:

~~~text
Deliver version 8.
Deliver duplicate version 8.
Deliver old version 7.
Deliver delete version 9.
Deliver old version 6.
```

Nếu events là **full state images**, version guard có thể giữ newest. Nếu events là **deltas**, cần sequence buffering/replay theo model, không bỏ older delta bừa bãi.

## 109. Test pyramid theo chi phí

Một lựa chọn:

~~~text
Pure model/generator tests: fast, many cases
Adapter integration with real DB: fewer, representative
Concurrent history and fault tests: targeted, expensive
Cross-region/failover/DR drills: periodic, controlled
```

Một in-memory fake không thể tự tái hiện:

- Quorum loss.
- Replica lag.
- Primary step-down.
- Networking.
- Disk durability.
- KMS outage.
- Clock step.
- Compaction.
- Multi-shard transaction semantics.

Phân lớp test rõ để không phóng đại độ tin cậy của một test đơn lẻ.

## 110. Testcontainers có ích nhưng không là distributed proof

Một MongoDB/Redis/Cassandra container có thể test:

- Driver mapping.
- Basic query/conditional operations.
- Indexes/schema.
- TTL trong scope.
- Serialization.
- Integration API contract.

Tuy nhiên một container đơn node **không kiểm cluster partition/quorum/failover**. Nếu cần replica set/multi-node behavior, phải cấu hình topology đại diện và chạy faults có kiểm soát.

## 111. Managed service emulator không đồng nhất cloud thật

Local DynamoDB/emulators có thể khác cloud về:

- Capacity throttling.
- Streams retention.
- Global Tables.
- PITR/export.
- IAM/KMS.
- Network latency.
- Region failure.
- Internal durability.

Ghi environment type trong test result: **in-memory, emulator, real managed service, fault cluster**. Pass trên emulator chỉ hỗ trợ những phần contract nó mô phỏng.

## 112. CI cần chia per-commit và nightly

Một chiến lược:

- **Per commit:** unit properties, seed cố định, regression shrunk traces.
- **Nightly:** random seeds nhiều tries, database adapter integration.
- **Pre-release:** concurrency/transaction histories và schema compatibility.
- **Periodic:** failover/partition/clock faults trên cluster sandbox.
- **After incident:** replay trace gây lỗi và thêm property ngăn tái diễn.

Kiểm budget CPU, network, write capacity và cleanup; không để PBT trên shared DB phá việc kiểm thử của team khác.

## 113. Flaky test có thể là bug thật

Một failure chỉ xuất hiện 1/100 runs có thể là:

- Race thật của SUT.
- Sai assumption consistency.
- Test harness/clock lỗi.
- Shared test namespace bị interference.
- Timeout do overloaded CI.
- Seed không capture interleavings.

Đừng thêm `Thread.sleep(5000)` và coi đã fix. Ghi exact history, compare read/write concerns, kiểm independent oracle và chạy controlled scheduler khi có thể.

## 114. Incident trở thành property

Incident:

~~~text
Projection had PAID/v12.
Consumer restarted.
Old PENDING/v10 overwrote v12.
```

Regression:

~~~text
apply(PAID,v12)
apply(PENDING,v10)
assert target == (PAID,v12)
```

Property mở rộng:

~~~text
For all full-state event sequences,
  applied sourceVersion never decreases
  under the given key/generation.
```

Sau đó sinh duplicates/out-of-order/delete, và giữ shrunk trace v12→v10 làm regression vĩnh viễn.

## 115. Counterexample cần được xác minh trước khi quy lỗi

Khi test báo vi phạm:

1. Xác định consistency contract và API mode.
2. Kiểm history invocation/completion.
3. Kiểm test namespace không có external writer.
4. Phân loại timeout/unknown commit.
5. Kiểm clocks/logging/record ordering.
6. Kiểm adapter/driver cache.
7. Reproduce với minimal history.
8. Xem topology/version/fault state.
9. Xác định invariant nào thật sự bị phá.
10. Lưu evidence rồi sửa implementation hoặc test oracle.

Một eventual read trả stale không mặc định là database mất dữ liệu.

## 116. Không sửa generator để che lỗi

Khi phát hiện collision do key chứa `#`, không chỉ bỏ `#` khỏi generator trừ khi schema **chính thức cấm và validate** ký tự ấy trên mọi entrypoint.

Tương tự, không bỏ duplicate delivery khỏi test vì “broker hiếm khi retry”. Nếu replay là một failure mode hợp lệ, bộ test cần giữ nó.

## 117. Model cũng phải version hóa theo nghiệp vụ

Ví dụ rule mới cho phép `PAID -> CANCELLED` với refund flow, trong khi rule cũ cấm.

Cần:

- Model version tương ứng business contract.
- Historical data compatibility.
- New operation states.
- Deployment expand/contract.
- Transaction/invariant updates.
- Regression traces theo từng version.
- Authorization/side-effect changes.

Không coi invariant cũ là chân lý nếu nghiệp vụ đã đổi; cũng không sửa model cùng SUT không có review độc lập.

## 118. Differential testing nhiều adapters

Cùng generated operations chạy qua:

~~~text
Reference model
  |- MongoDB adapter
  |- DynamoDB adapter
  |- in-memory implementation
```

So normalized **business outcomes** chứ không raw driver metadata. Phải hạn chế vào **common supported semantics**: ví dụ DynamoDB GSI eventual view và MongoDB strong primary read có thể khác được phép.

Differential testing tốt giúp tìm bug ở serialization, key encoding, CAS và tombstone khi chuyển engine.

## 119. Migration property

Với data migration v1→v2:

~~~text
model(v1) -> canonical business state
transform(v1) -> v2
readTarget(v2) -> same canonical business state
```

Kiểm:

- Tenant/key identity.
- Monetary totals.
- Source version.
- TTL/expiry.
- Delete representation.
- Idempotent re-import.
- Search projection eligibility.
- No PII leakage into target.

Không bắt raw JSON equality khi schema mới cố ý đổi representation.

## 120. Multi-model NoSQL projection

Nếu cùng source tạo document và graph projection:

- Edges trỏ đúng nodes.
- Graph traversal không xuyên tenant boundary.
- Duplicate events không tạo duplicate edge theo contract.
- Delete node xử lý edges theo policy.
- Out-of-order events không resurrect.
- Rebuild từ snapshot+events hội tụ.

Một simple key-value model không đủ để kiểm graph path semantics; cần graph model chuyên biệt nếu traversal là business-critical.

## 121. Materialized view eventual convergence

Sau khi source dừng ghi và projection nhận đủ events qua watermark:

- Eligible records xuất hiện.
- Deleted records không xuất hiện.
- Version không lùi.
- Tenant isolation giữ.
- No duplicate logical rows.
- Queries hợp filter/sort.
- Current projection state khớp model.

Không đòi immediate visibility khi service cam kết refresh bất đồng bộ.

## 122. Reshard/repartition tests

Khi đổi partition mapping:

~~~text
Source partition P -> target P1, P2
```

Sinh keys sát ranh giới, large partitions, hot tenants, moves. Properties:

- No gap.
- No double-authoritative owner.
- State/version preserved.
- Delete/tombstone preserved.
- Concurrent writes không bị skip.
- Target routing deterministic.
- Recovery/cutover không dùng stale checkpoint.

Uniform random keys hiếm khi chạm boundary; cần generator bias.

## 123. Schema compatibility properties

Reader mới có thể cần giải mã v1, v2, v3 trong migration window.

Property:

~~~text
For every supported schema version:
  decode -> canonical domain state
  or an explicitly documented rejection.
```

Không silently parse malformed v1 thành default/null rồi overwrite dữ liệu đúng.

## 124. Audit và log correctness

Một successful mutation có thể cần:

- Source version và operation ID.
- Trusted actor/tenant.
- Audit event theo outbox/transaction contract.
- Không log secrets/PII bị cấm.
- Retry không tạo contradictory audit.
- Timestamps không tự thay source sequence.

Nếu audit được publish bất đồng bộ, test hội tụ theo watermark thay vì yêu cầu immediate event tồn tại ở mọi sink.

## 125. Backup/restore property

Sau restore tại snapshot boundary:

- Data/key sets khớp source snapshot semantics.
- Versions và tombstones còn đúng.
- Indexes/query behavior được phục hồi.
- Key encryption metadata usable.
- CDC resume/checkpoint hợp lệ.
- Coordination/fencing epochs không bị hồi quy.
- Schema decoder hỗ trợ historical data.
- Không trigger duplicate external side effects trên replay.

Checksum file backup không thay được restore-and-validate test.

## 126. Authority snapshot rollback

Một lease authority từng cấp term 100, rồi restore snapshot về term 80. Worker cũ còn giữ token 90.

Property quan trọng:

~~~text
After recovery to a fresh generation/epoch,
no old owner can commit a protected mutation.
```

Test cả stale worker vẫn hoạt động khi cluster mới phục hồi. Reboot tất cả workers có thể bỏ sót đúng failure mode.

## 127. Timestamp không tự là business version

Sinh clients có:

- Clock fast/slow.
- Same timestamp milliseconds.
- Future timestamp.
- Failover.
- Backfill replay.
- Retry.

Nếu implementation dùng `updatedAt` do client gán để CAS, test có thể phát hiện lost update. Cách giải thường dùng **source monotonic version/conditional mutation**, không chỉ tăng precision clock.

## 128. Lease/fencing model

Reference state:

~~~text
resourceId
generation
authoritativeTerm
leaseHolder
leaseValidity
sinkAcceptedTerm
businessState
```

Sinh A acquire, A pause, B acquire, A late write. Kiểm sink gating theo protocol. Lưu ý: nếu sink chỉ so token với **max token đã từng nhìn thấy**, A có thể qua trước khi first B write tới sink; cần test chính race này.

## 129. CRDT vs LWW

Nếu datatype dùng semilattice merge, PBT có thể kiểm commutative, associative, idempotent. Với LWW dựa timestamp, những tính chất business như “write thực tế mới hơn phải thắng” không tự được bảo đảm khi clocks lệch.

Model phải theo **merge/conflict semantics thật**, không gắn nhãn CRDT chỉ vì storage là NoSQL.

## 130. Replay horizon và idempotency retention

Nếu idempotency key sống 24h mà message có thể replay sau 72h, duplicate business effect có thể xuất hiện.

PBT/state model cần sinh `replayAfterExpiration`, xác định:

- Operation ID scope.
- Max replay window.
- Dedupe retention.
- Downstream provider policy.
- Long outage/archival reprocessing.
- Generation/epoch.

Không hứa exactly-once forever nếu dedupe record có TTL ngắn.

## 131. Pagination khi dataset đang thay đổi

Với live dataset, no-duplicate/no-missing across pages không phải property mặc định. Một API muốn bảo đảm điều này phải có cơ chế phù hợp: snapshot cursor, stable keys/dedupe, revision token hoặc contract chấp nhận visibility anomalies.

Test phải biết **quy tắc API khi insert/delete xảy ra giữa pages**, không so với snapshot tưởng tượng.

## 132. Batch partial success và crash

Sinh batch writes, inject partial failure, crash trước checkpoint, restart và replay.

Assert:

- Durable disposition của mỗi item.
- Không checkpoint qua pending/unknown items.
- Retry idempotent.
- Version guard ngăn stale overwrite.
- Quarantine poison records.
- Outcomes được phân loại đúng.

Không coi “bulk API trả request success” là mọi item đã được ghi.

## 133. Security outcome không chỉ là HTTP code

API có thể trả `404` thay vì `403` để không lộ sự tồn tại của record tenant khác. Property vẫn cần kiểm:

- Cross-tenant update/delete không tác động thật.
- Cursor không rò key/field.
- Counts/search không lộ thông tin trái quyền.
- Audit theo policy.
- Cache không dùng key collision.

Không chỉ assert `status == 404` rồi coi tenant isolation đã được chứng minh.

## 134. Cache invalidation model

Sinh:

~~~text
Read misses cache.
Source updates.
Cache key invalidated.
Read again.
```

Properties tùy consistency:

- No cross-tenant cache collision.
- Negative cache invalidated on create.
- TTL không kéo dài trái business policy.
- Cache warm/cold không thay authoritative mutation.
- Version metadata không đi lùi nếu contract cấm.
- Eventual convergence sau invalidation.

Nếu cache chủ đích stale, cần freshness bound/allowed observations thay vì immediate equality.

## 135. Privacy deletion end-to-end

Một yêu cầu xóa dữ liệu có thể cần lan tới source, Search, cache, analytics. State model nên theo dõi deletion version và completion watermark.

Test:

- Read access bị từ chối theo policy.
- Late CDC event không resurrect.
- Target không giữ plain PII ngoài retention/exception.
- Backup/erasure policy được áp dụng.
- API không báo hoàn tất nếu còn stage bắt buộc pending theo contract.

Đây có thể là **eventual workflow** chứ không một transaction xuyên mọi systems.

## 136. Observability cũng có property

Inject KMS error, CAS conflict hoặc unknown write response; assert:

- Không fail-open lưu plaintext.
- Stale conflict không retry vô hạn.
- Unknown commit không bị biến thành definite failure.
- Trace/operation ID có thể tìm lại outcome.
- Không log raw PII/secrets.
- Rate limiter không tự mở unlimited concurrency.

Một correctness suite mạnh kiểm **hành vi khi thất bại**, không chỉ business data cuối cùng.

## 137. Partition metamorphic relation

Với snapshot bất biến, nếu ranges \(R_1,\dots,R_n\) thực sự phủ keyspace không gap:

\[
query(All)=merge(query(R_1),...,query(R_n))
\]

theo semantics filter/order/aggregation.

Rất hữu ích cho scan/backfill/reshard; nhưng `topK` hoặc cross-partition aggregate cần merge algorithm đúng, không đơn thuần nối lists.

## 138. Backfill replay idempotence

Cho historical full-state events có source version:

~~~text
apply(history)
apply(history again)
```

Business state cuối phải tương đương nếu target conditional/idempotent. Physical write counts và attempt logs có thể khác.

Thử thêm replay đảo event order theo phạm vi source ordering cho phép. Nếu dữ liệu là delta, version gap phải được xử lý riêng.

## 139. Batch-size metamorphic relation

Một tập independent full-state mutations có per-key version guard có thể apply batch-size 1, 10, 100 và cho cùng normalized state.

Chỉ hợp lệ khi batch grouping không ảnh hưởng transactional requirements, events không dependent theo aggregate và no-gap coverage được đảm bảo.

## 140. Steady-state projection property

Source → CDC → Search là eventual pipeline. Chỉ khi:

- Source quiesces.
- Dependencies hồi phục.
- All events through watermark W are durably applied.
- Refresh/visibility gate achieved.

mới so target với source at W. Trong giai đoạn lag, những **safety requirements như tenant isolation** vẫn phải giữ ngay, không được trì hoãn theo eventual convergence.

## 141. Reference oracle phải độc lập

Sai:

~~~text
expected = sameDatabaseQuery()
actual = apiUsingSameDatabaseQuery()
```

vì cả hai có thể cùng sai do filter thiếu tenant predicate.

Tốt hơn:

- Sinh dataset từ model.
- Expected từ in-memory canonical states.
- Independent query implementation hoặc known snapshots.
- Contract-based normalization.
- Regression trace từ các lỗi thật.

## 142. Test preconditions phải tự kiểm

Trước khi kết luận consistency violation, xác nhận:

- Cluster topology đúng.
- Read/write concerns/config flags đúng.
- Không external writers cùng namespace.
- Feature được bật.
- Test clock/history recorder hợp lệ.
- Source/key identity nhất quán.
- Session/transaction scope đúng.
- Fault injection thực sự có hiệu lực.

Nếu preconditions fail, kết quả là **invalid environment/test setup**, không tự gọi database bug.

## 143. Một ma trận operation/property

| Operation | Generated inputs | Property |
|---|---|---|
| Create | Duplicate IDs, tenants, malformed | Uniqueness/isolation |
| Get | Missing/deleted/stale replica | Read consistency contract |
| Update | Fresh/stale versions, null patch | Atomic CAS/no lost update |
| Delete | Delete twice, late upsert | Tombstone/no resurrection |
| Query | Filter/sort/pagination/tampered cursor | Correct coverage/authorization |
| Batch | Partial success/retries | Durable dispositions |
| Transaction | Cross-key conflicts/write skew | Isolation/invariant |
| TTL | Boundary/cleanup delayed | Business expiry |
| Counter | Duplicate increment/overflow | Idempotency/conservation |
| CDC | Duplicate/reorder/gap | Source ordering/convergence |
| Migration | Old schema/live writes | Backfill correctness |
| Failover | Partition/restart/stale leader | Safety/liveness |

## 144. Document testing scope

Một báo cáo:

~~~text
Consistency: per-key linearizability
Writes: conditional update
Reads: supported strong mode
Clients: 8
History: 200 operations
Faults: leader restart and network delay
Runs: 1,000 histories

Not tested:
  Multi-key serializability
  Cross-region split-brain
  72-hour CDC replay
  Long-term TTL retention
```

Ghi **không phát hiện phản ví dụ trong scope** chính xác hơn tuyên bố đã chứng minh hệ luôn an toàn.

## 145. Counterexample thành regression và property

Khi tìm thấy bug:

1. Lưu shrunk history.
2. Lưu seed, versions, topology, consistency mode.
3. Tái hiện và loại test setup error.
4. Ghi root cause.
5. Tạo deterministic regression.
6. Giữ generalized property.
7. Test adapter sau fix.
8. Chạy các edge cases lân cận.
9. Thêm property vào CI gate nếu critical.
10. Cập nhật model khi business contract đổi.

## 146. Resource budget cho CI suite

Một property chạy 200 tries × 80 commands đã tạo 16.000 operations trước retries/shrinking. Với DB thật, phải tính quota/IO/network và cleanup.

Thiết kế:

- Per-commit fast unit suite.
- Nightly deeper integration.
- Dedicated sandbox for fault tests.
- Timeout/rate/concurrency caps.
- Failing histories được lưu an toàn.
- Unique test namespace.
- No real payment/email side effect.
- Delete only owned fixtures.

## 147. Kiểm thử model và harness

Model cũng có thể sai. Cần example tests cho từng transition, kiểm shrinker giữ dependencies, kiểm history collector và normalization comparator, và review invariants độc lập.

Một thử nghiệm hữu ích là **mutation testing** trên toy adapter:

- Cố ý bỏ version condition.
- Bỏ tenant predicate.
- Reset TTL.
- Bỏ tombstone.
- Duplicate increment.
- Skip pagination item.
- Swallow delete event.

Property suite tốt phải phát hiện được những lỗi đó. Đây không phải content QA của bài học, mà là **kỹ thuật kiểm thử phần mềm** được giới thiệu cho người học.

---

## 148. Bài thực hành tổng hợp: Inventory bằng reference model

Một Inventory API Java sử dụng MongoDB document hoặc DynamoDB item làm **nguồn có thẩm quyền**:

~~~text
State: sku, available, reserved, version, processedOperationIds
Commands:
  Restock(opId, qty)
  Reserve(opId, qty)
  CancelReservation(opId, qty)
  Read()
```

Viết model thuần không phụ thuộc SDK, rồi triển khai adapter có conditional writes. Sinh quantities biên (0, 1, negative, max), duplicate operation IDs, concurrent reserves, crash sau commit và retry sau mất ACK. Properties:

- `available >= 0` và `reserved >= 0`.
- Bảo toàn stock theo nghiệp vụ được định nghĩa.
- Invalid quantity không thay authoritative state.
- Cùng idempotency key không làm effect trùng.
- CAS stale write không ghi đè state mới.
- Two reserves for final item không cùng thành công.
- Sau recovery, state và ledger còn nhất quán.

Thử nhanh model với hàng nghìn sequences, sau đó chạy **integration, concurrent history và fault tests** trên sandbox. Không gọi pass của một test in-memory là chứng minh multi-node safety.

## 149. Bài tập A — Example hay property?

**Tình huống:** `reserve(stock=10, qty=3) → remaining=7`. **Hỏi:** đã là PBT chưa?

**Hướng giải:** đây là một example. Property sinh nhiều `stock >= 0`, `qty > 0`, kiểm thành công/remaining hoặc reject/no-state-change theo điều kiện `qty <= stock`.

## 150. Bài tập B — Conservation

**Tình huống:** `initial=10`, `restocked=5`, `available=8`, `reserved=4`, `sold=3`. **Hỏi:** conservation còn giữ?

**Hướng giải:** \(8+4+3=15=10+5\), đúng trong mô hình giả định; nếu có refund/lost/damaged phải thêm đại lượng tương ứng.

## 151. Bài tập C — Invalid quantity

**Tình huống:** generator sinh `reserve(-2)` cho stock=4. **Hỏi:** bỏ command?

**Hướng giải:** không; kiểm validation rejection và authoritative state không đổi. Chỉ giới hạn domain nếu validation được kiểm ở lớp khác và input type không cho âm.

## 152. Bài tập D — Shrinking

**Tình huống:** failure sau 500 commands rút còn `create(K), delete(K), staleUpsert(K)`. **Hỏi:** ý nghĩa?

**Hướng giải:** phản ví dụ nhỏ cho delete resurrection; cần giữ model preconditions khi shrink và biến trace thành deterministic regression.

## 153. Bài tập E — Seed không tái hiện race

**Tình huống:** seed 123 sinh cùng commands nhưng chỉ fail vài lần. **Hỏi:** vì sao?

**Hướng giải:** seed không điều khiển thread scheduler/network. Ghi invocation/completion history, fault schedule và dùng synchronization hooks khi có thể.

## 154. Bài tập F — Composite key collision

**Tình huống:** `(a#b,c)` và `(a,b#c)` cùng mã hóa thành `a#b#c`. **Hỏi:** property nào hỏng?

**Hướng giải:** injective encoding/round-trip. Dùng escaping hoặc length-prefix/structured key serialization.

## 155. Bài tập G — Null với missing

**Tình huống:** query/index phân biệt `{x:null}` và `{}`. **Hỏi:** generator chỉ tạo x non-null đã đủ?

**Hướng giải:** chưa; thêm missing, explicit null, empty string, type mismatch và oracle cho từng trường hợp.

## 156. Bài tập H — Tenant isolation

**Tình huống:** tenant A/B cùng có user U1. Query của A thiếu tenant predicate. **Hỏi:** status 200 chứng minh đúng?

**Hướng giải:** không. Kiểm IDs/ownership, cross-tenant mutation denial, cursor/cache/search isolation và audit behavior.

## 157. Bài tập I — Unknown payment outcome

**Tình huống:** `CreatePayment(K,100)` commit rồi ACK mất; client retry cùng K. **Hỏi:** có thể charge hai lần?

**Hướng giải:** không nếu contract có idempotency; cần authoritative operation ledger/provider idempotency và reconcile timeout. Không coi timeout chắc chắn là abort.

## 158. Bài tập J — Same key khác payload

**Tình huống:** cùng idempotency key K, lần sau amount=900 thay vì 100. **Hỏi:** xử lý?

**Hướng giải:** trả conflict theo contract, không coi là replay hợp lệ và không áp business effect thứ hai.

## 159. Bài tập K — Concurrent CAS

**Tình huống:** hai writers cùng `expectedVersion=5`. **Hỏi:** outcome?

**Hướng giải:** với atomic CAS trên cùng key, tối đa một transition từ v5 sang v6 thành công; reconcile ambiguous timeouts trước khi kết luận winner.

## 160. Bài tập L — Check-then-write

**Tình huống:** A và B cùng đọc version5; B ghi version8, A ghi version7 sau. **Hỏi:** lỗi?

**Hướng giải:** stale overwrite do check ở Java không atomic; dùng conditional mutation trong DB.

## 161. Bài tập M — MongoDB TTL

**Tình huống:** session expired nhưng document chưa bị TTL monitor xóa. **Hỏi:** property physical delete ngay tại expiry có đúng?

**Hướng giải:** không. Business authorization expiry cần kiểm riêng, TTL cleanup bất đồng bộ.

## 162. Bài tập N — DynamoDB GSI stale

**Tình huống:** base table write success; query GSI ngay chưa thấy item. **Hỏi:** linearizability violation?

**Hướng giải:** không tự kết luận; GSI read semantics khác strong read path. Test đúng consistency mode và eventual catch-up.

## 163. Bài tập O — Overlapping operations

**Tình huống:** B get bắt đầu khi A put chưa trả ACK; B thấy giá trị cũ. **Hỏi:** chắc sai linearizability?

**Hướng giải:** chưa. Operations overlap, read có thể linearize trước write.

## 164. Bài tập P — Non-overlapping operations

**Tình huống:** A put success xong; sau đó B get mới bắt đầu và thấy old value, không concurrent write khác. **Hỏi:** khi nào sai?

**Hướng giải:** nếu read/write là linearizable register cùng key và ACK semantics đảm bảo commit; eventual read có thể cho phép stale.

## 165. Bài tập Q — Pending operation

**Tình huống:** checker loại một write timeout khỏi history như definite failure. **Hỏi:** đúng không?

**Hướng giải:** không; write có thể đã commit. Model phải xử lý pending/unknown possibilities và reconcile.

## 166. Bài tập R — Serializability

**Tình huống:** history serializable nhưng thứ tự real-time của non-overlapping transactions bị đảo. **Hỏi:** serializability chắc sai?

**Hướng giải:** không; strict serializability mới yêu cầu giữ real-time order đó.

## 167. Bài tập S — Write skew

**Tình huống:** hai transactions cùng đọc “ít nhất một doctor on call”, rồi mỗi transaction tắt một doctor khác. **Hỏi:** anomaly gì?

**Hướng giải:** write skew có thể xảy ra dưới isolation không serializable; checker phải xem read/write dependencies.

## 168. Bài tập T — Increment replay

**Tình huống:** `increment(1)` commit, ACK mất, client retry. **Hỏi:** counter tăng mấy lần?

**Hướng giải:** business intent idempotent cần tăng một lần, nhưng native increment không tự an toàn; cần dedupe/ledger.

## 169. Bài tập U — CRDT idempotence

**Tình huống:** `merge(a,a) != a`. **Hỏi:** property nào bị phá?

**Hướng giải:** idempotence của merge, duplicate state delivery có thể làm sai state; kiểm cả commutativity/associativity theo protocol.

## 170. Bài tập V — Full-state CDC

**Tình huống:** target đã có v9, nhận full image v7. **Hỏi:** làm gì?

**Hướng giải:** atomic version guard phải skip v7, tránh stale overwrite.

## 171. Bài tập W — Delta CDC reorder

**Tình huống:** counter delta v11 đến trước v10, sink bỏ v10 vì version nhỏ. **Hỏi:** đúng không?

**Hướng giải:** không nhất thiết; delta cần contiguous sequence/buffer/replay hoặc authoritative full-state re-read.

## 172. Bài tập X — Tombstone

**Tình huống:** delete K v11 đã áp; historical upsert v10 đến sau. **Hỏi:** kết quả?

**Hướng giải:** K không được resurrect; giữ deletion version/tombstone theo replay horizon.

## 173. Bài tập Y — Pagination

**Tình huống:** dataset 100 keys, page size 13, nhận đủ 8 pages. **Hỏi:** count đã chứng minh đúng?

**Hướng giải:** chưa; so concat pages với reference sorted filtered set, không duplicate/skip và cursor phải kết thúc.

## 174. Bài tập Z — Same version, different payload

**Tình huống:** hai events cùng v12 nhưng payload khác. **Hỏi:** chọn last arrival?

**Hướng giải:** không theo nguồn version đơn điệu; quarantine/investigate generation/source/transformer.

## 175. Bài tập AA — In-memory fake

**Tình huống:** fake pass 10.000 tries. **Hỏi:** chứng minh failover an toàn?

**Hướng giải:** không; cần real DB integration, multi-node faults và history checker.

## 176. Bài tập AB — Single-node container

**Tình huống:** MongoDB một container pass CAS. **Hỏi:** đã test election?

**Hướng giải:** chưa; cần replica-set topology, read/write concern và failover tests.

## 177. Bài tập AC — Model dùng chung code SUT

**Tình huống:** model và SUT cùng gọi `calculateAvailable()` có bug. **Hỏi:** rủi ro?

**Hướng giải:** cùng sai nên comparator pass; model/oracle cần đủ độc lập và có example tests.

## 178. Bài tập AD — Mutation testing

**Tình huống:** cố tình bỏ tenant condition trong toy adapter, nhưng PBT vẫn pass. **Hỏi:** kết luận?

**Hướng giải:** generator/oracle chưa kiểm cross-tenant access; cần tăng coverage cho tenant collisions, negative commands và state effects.

## 179. Bài tập AE — Dedupe retention

**Tình huống:** idempotency entries giữ 24 giờ, events replay được sau 72 giờ. **Hỏi:** có thể double effect?

**Hướng giải:** có. Retention của dedupe không bao phủ replay horizon nếu không có guard khác.

## 180. Bài tập AF — Rollback sau cutover

**Tình huống:** sau cutover ghi vào DB v2; rollback đọc về v1 không reverse CDC. **Hỏi:** risk?

**Hướng giải:** các acknowledged writes mới không có ở v1. Cần authority/failback synchronization plan đã kiểm.

---

## 181. Checklist thiết kế property-based và stateful tests cho NoSQL

**Định nghĩa hệ và oracle**

1. Đã nêu nguồn dữ liệu có thẩm quyền cho mỗi aggregate chưa?
2. Đã nêu consistency model của từng read/write path chưa?
3. Có phân biệt single-key atomicity với multi-key transaction không?
4. Invariant có phản ánh contract, không chỉ implementation hiện tại không?
5. Các business exceptions được mô hình hóa rõ không?
6. Reference model có độc lập với production code không?
7. Model có unit tests cho những transitions quan trọng không?
8. Có ghi state machine và preconditions từng command không?
9. Có phân biệt safety và liveness properties không?
10. Có xác định phạm vi key/tenant/shard/region của invariant không?
11. Có phân biệt definite success, definite rejection và unknown commit không?
12. Có định nghĩa normalization để so business state đúng không?

**Generators và shrinking**

13. Generators có sinh new/duplicate IDs không?
14. Có bias về hot keys để tăng va chạm không?
15. Có sinh cross-tenant accesses/collisions không?
16. Có sinh null, missing, empty và malformed values không?
17. Có sinh zero, negative, overflow và decimal boundaries không?
18. Có Unicode/locale/case/normalization cases không?
19. Có sinh stale/duplicate/large source versions không?
20. Có commands cho create/update/delete/recreate/retry không?
21. Có valid và deliberately invalid commands không?
22. Có sinh chuỗi dài với transitions hiếm không?
23. Có sinh operation IDs trùng payload và khác payload không?
24. Có TTL boundary/expired-but-present records không?
25. Có generator event reorder/duplicate/gap không?
26. Có giữ seed và shrunk trace khi fail không?
27. Shrinker có giữ preconditions/happens-before constraints không?
28. Có transition coverage chứ không chỉ đếm tries không?
29. Có test generator không bỏ mất corner cases đã biết không?

**NoSQL data semantics**

30. Atomic CAS có được kiểm tại source commit boundary không?
31. Có kiểm stale write không ghi đè source version mới hơn không?
32. Có kiểm tombstone/delete không bị resurrect không?
33. Có test key generation/ABA/deleted-recreated identity không?
34. Có kiểm idempotent commands và dedupe retention không?
35. Có kiểm counter increment retry sau lost ACK không?
36. Có thử batch partial success và checkpoint-after-commit không?
37. Có phân biệt full-state events và delta/patch events không?
38. Có kiểm contiguous sequence/gaps trong CDC không?
39. Có test snapshot + CDC no-gap theo engine capability không?
40. Có test cursor pagination cùng stable ordering/snapshot rules không?
41. Có test index/search refresh-watermark semantics không?
42. Có test source schema migration/old format decode không?
43. Có kiểm composite key encoding injective không?
44. Có kiểm tenant isolation trên queries, writes, cursors, cache không?
45. Có tránh xem TTL async deletion như authorization guarantee không?
46. Có kiểm read/write concern khác nhau theo engine không?
47. Có phân biệt eventual convergence với immediate strong visibility không?
48. Có test transaction write skew và isolation nếu nghiệp vụ cần không?
49. Có thử CRDT merge laws nếu data type dùng CRDT không?
50. Có thử failback/rollback khi source authority đổi không?

**Concurrency và fault history**

51. Có ghi invocation/completion order cho mỗi operation không?
52. Có lưu operationId/clientId/key/generation cho history không?
53. Có xử lý timeout như ambiguous thay vì definite abort không?
54. Có test hai CAS writers cùng expectedVersion không?
55. Có controlled pause/scheduler để tạo race mục tiêu không?
56. Có test process crash sau commit trước ACK/checkpoint không?
57. Có test leader failover và network partitions không?
58. Có test stale owner sau lease expiration và GC pause không?
59. Có xét fencing token visibility race tại sink không?
60. Có test restore snapshot rollback epoch/term không?
61. Có kiểm linearizability theo đúng object/API scope không?
62. Có tránh so `nanoTime()` của các hosts độc lập không?
63. Có dùng checker phù hợp cho multi-key transactional histories không?
64. Có test convergence sau quiescence với bounded observability không?
65. Có lưu fault timeline/topology để replay không?

**Môi trường, chi phí và CI**

66. Mỗi test run có isolated namespace và quyền tối thiểu không?
67. Có ngăn random writes tới production và external side effects không?
68. Có giới hạn tries, concurrency, rate, memory và cost không?
69. Có cleanup chỉ những resources thuộc test run không?
70. Có phân biệt fake/emulator/real DB/fault cluster trong báo cáo không?
71. Có test driver/engine versions thực tế không?
72. Có reproducibility artifacts an toàn, không chứa secrets/PII không?
73. Có replay known counterexamples trong per-commit suite không?
74. Có nightly deep randomized runs và periodic fault tests không?
75. Có phát hiện flaky harness và shared environment interference không?
76. Có xem root cause thay vì tăng sleep để che race không?
77. Có mutation tests cho một số invariant trọng yếu không?
78. Có baseline monitoring để tránh suite phá SLO sandbox không?
79. Có quy trình review model khi business contract thay đổi không?
80. Có ghi giới hạn những điều test **chưa chứng minh** không?

Không phải hệ nào cũng phải dùng tất cả 80 mục. Chọn mục theo **data criticality, consistency requirements, compliance, failover model và chi phí kiểm thử**, nhưng không bỏ qua ambiguity của timeouts, tenant scope hoặc retries khi chúng có thể làm sai dữ liệu.

## 182. Mẫu hợp đồng property/state model

~~~yaml
testSuite:
  name: inventory-nosql-correctness
  language: Java
  frameworks:
    propertyBased: jqwik
    exampleRegression: JUnit
    distributedHistory: selectedCheckerByContract
  environments:
    unit:
      dataStore: pureReferenceModel
      randomTries: boundedAndFast
    integration:
      dataStore: isolatedRealOrEmulatedNoSql
      namespace: uniquePerRun
      credentials: leastPrivilege
    faultCluster:
      dataStore: dedicatedMultiNodeTestDeployment
      productionTraffic: forbidden
  dataContract:
    sourceOfTruth: InventoryAggregate
    keyScope:
      - tenantId
      - sku
      - generation
    readConsistency: documentedPerOperation
    writeConsistency: documentedPerOperation
    businessInvariants:
      - availableNonNegative
      - reservedNonNegative
      - versionMonotonicForGeneration
      - tenantIsolation
      - exactlyOneBusinessEffectPerOperationIdWithinPolicy
    failureOutcomes:
      - definiteSuccess
      - definiteBusinessRejection
      - transientFailure
      - unknownCommit
  referenceModel:
    state:
      - available
      - reserved
      - version
      - processedOperationIds
    commands:
      - Restock
      - Reserve
      - CancelReservation
      - Read
    expectedResults:
      - applied
      - rejected
      - staleVersion
      - alreadyApplied
      - notFound
      - unknown
    independentOfSutImplementation: true
  generators:
    quantityCases:
      - zero
      - one
      - negative
      - normal
      - overflowBoundary
    identifierCases:
      - duplicate
      - unicode
      - compositeKeySeparator
      - crossTenantCollision
    statefulSequences:
      - createUpdateDelete
      - retryAfterCommit
      - retryAfterUnknown
      - deleteThenStaleUpsert
      - concurrentReserveLastItem
    distributions:
      hotKeys: deliberatelyBiased
      invalidCommands: deliberatelyIncluded
    shrinking:
      preservePreconditions: true
      preserveRealTimeHistoryConstraints: true
  correctness:
    directProperties:
      - versionCasSingleWinner
      - noNegativeAvailable
      - idempotentReserveOperation
      - tenantIsolation
    temporalProperties:
      - noDeleteResurrection
      - sourceVersionNeverDecreases
    convergenceProperties:
      - targetMatchesSourceAfterWatermark
    consistencyChecking:
      scope: perKeyWhenSupported
      model: chosenByDocumentedApiGuarantee
      unknownCommit: trackedAsAmbiguous
  faults:
    - retryDuplicate
    - lostAckAfterCommit
    - processCrash
    - primaryStepDown
    - networkPartition
    - gcPauseBeyondLease
    - staleFencingToken
    - expiredTtlStillPresent
    - snapshotRestore
  evidence:
    onFailure:
      - seed
      - shrunkHistory
      - invocationCompletionEvents
      - operationIdsAndVersions
      - driverAndServerVersion
      - consistencySettings
      - topologyAndFaultTimeline
      - testNamespace
    secretsAndPii: redacted
  cicd:
    perCommit:
      - fastProperties
      - knownCounterexamples
    nightly:
      - randomizedIntegration
      - targetedConcurrency
    periodic:
      - faultHistories
      - backupRestore
    resourceLimits:
      inFlight: bounded
      attempts: bounded
      dataRetention: testOnly
~~~

Đây là **YAML mô tả chiến lược và hợp đồng kiểm thử**, không phải cấu hình chạy nguyên xi của jqwik, JUnit, Jepsen hoặc một NoSQL driver. Từng `property` cần được chuyển thành Java test/oracle cụ thể có preconditions, environment setup và outcome rules.

## 183. Runbook khi PBT tìm thấy counterexample

~~~text
TRIGGER
  Property-based or model-based suite reports a violation.

PRESERVE
  1. Save seed and shrunk command history.
  2. Save invocation/completion with operation IDs.
  3. Capture DB/driver/schema versions and topology.
  4. Capture consistency modes, fault timeline and run ID.
  5. Redact personal data and sensitive credentials.

VERIFY TEST VALIDITY
  6. Check the property matches documented consistency.
  7. Check reference model independently against known examples.
  8. Check the test namespace has no unrelated writers.
  9. Classify unknown commits, timeouts and retries.
 10. Confirm history collection/timestamps have correct ordering.

REPRODUCE
 11. Replay the shrunk example in an isolated environment.
 12. If nondeterministic, add controlled scheduling/barriers.
 13. Reduce keys, operations and faults without changing bug.
 14. Check engine/driver configuration and permissions.

ASSESS IMPACT
 15. Determine if the failure risks data loss, privacy, finance,
     duplicate side effects, staleness or availability.
 16. Stop unsafe deployments/cutover if invariant is critical.
 17. Compare against production incident/metrics where allowed.

FIX AND PREVENT
 18. Fix SUT or model contract with independent review.
 19. Add a deterministic regression for minimal history.
 20. Keep generalized property and failure generator.
 21. Run impacted adapters, engine configurations and fault modes.
 22. Update CI gates, runbook and model version.
~~~

Nếu phát hiện mất tính đúng đắn ở nguồn dữ liệu, **không chỉ sửa test để xanh**. Cần đánh giá blast radius dữ liệu hiện có, reconciliation và remediation. Nhưng nếu bug nằm ở test oracle (ví dụ áp linearizability cho eventual replica read), phải sửa property theo contract, không quy lỗi tùy tiện cho engine.

## 184. Cách đưa vào một dự án Java NoSQL thật

Một trình tự thực hiện hợp lý:

1. Chọn một aggregate quan trọng, ví dụ Inventory, Order hoặc Session.
2. Viết **5–10 invariants có thể phát biểu chính xác**.
3. Viết reference model thuần với states/commands/outcomes.
4. Chạy model examples để bảo đảm transitions có chủ đích.
5. Viết generators theo domain và cố ý tăng duplicate/hot-key cases.
6. Viết property tests thuần cho transform/key encoding/serialization.
7. Viết stateful sequence runner với `@Property`.
8. Tạo adapter cho database sandbox; so normalized state.
9. Thử stale CAS, delete, TTL, event replay và unknown commit.
10. Thêm controlled concurrent history với invocation/completion logs.
11. Chọn consistency checker theo scope API, không đoán.
12. Bổ sung failure injection/restore theo risk.
13. Tự động lưu seed/shrunk trace, bảo vệ PII và có regression.
14. Phân tầng per-commit/nightly/periodic test, giới hạn tài nguyên.

**Ví dụ:** nếu model phát hiện `Create→Delete→BackfillOldVersion` làm record sống lại, một sửa đúng có thể là versioned tombstone ở target và atomic conditional apply, không đơn giản làm consumer “chạy nhanh hơn”. PBT giúp tìm ra **dấu hiệu và minimal history**, còn thiết kế database phải giải nguyên nhân.

## 185. Kết luận

**Property-based testing** và **model-based testing** giúp chuyển yêu cầu tính đúng của Database No SQL thành những *quy luật có thể thực thi*. Thay vì chỉ thử một input đẹp, ta sinh nhiều documents, tenants, versions, retries và sequences; sau đó giữ counterexample nhỏ để thấy một bug thật.

Những điều đáng nhớ:

- **Property** nêu quy luật; **reference model** dự đoán transition; **generator** tìm trường hợp; **shrinking** thu gọn lỗi.
- **Stateful tests** bắt được lỗi qua chuỗi `Create→Update→Delete→Retry`, nơi test từng API đơn lẻ dễ bỏ sót.
- **Atomic CAS, idempotency, tombstones và domain versions** là những điểm thường cần kiểm dưới concurrent writes.
- **Consistency model quyết định oracle**: không ép eventual reads phải giống strongly consistent reads ngay lập tức.
- **Linearizability/serializability history tests** cần invocation/completion events, xử lý unknown outcomes và phạm vi bảo đảm chính xác.
- **Fault injection** với network partition, lost ACK, GC pause, failover và replay khám phá những interleavings hiếm.
- **NoSQL engine khác nhau** về timestamp, transactions, TTL, batch partial success, Streams và read visibility; adapter phải giữ semantics riêng.
- **Seed và shrunk history** cần đi kèm topology/driver version/fault timeline để tái hiện được concurrency bugs.
- **Bộ test và reference model cũng phải được kiểm tra tính độc lập**, không tự nhận đã chứng minh tính đúng tuyệt đối sau một số lượng random cases.
- **Production safety** phải được bảo vệ: chạy trên isolated sandbox, bounded resource budgets và không gây business side effects thật.

> **Một test tốt không chỉ hỏi “request này trả gì?”, mà hỏi “qua mọi chuỗi thao tác và lỗi hệ thống nằm trong hợp đồng, có trạng thái nào bị cấm lại có thể xuất hiện không?”**

Khi mô hình trạng thái, generator, lịch sử concurrent operations và chính sách consistency được viết rõ, người học có thể biến những rủi ro mơ hồ như “thi thoảng mất update” thành **phản ví dụ tái hiện được**, rồi dùng chúng làm rào chắn hồi quy mỗi khi schema, driver, topology hoặc logic nghiệp vụ thay đổi.
