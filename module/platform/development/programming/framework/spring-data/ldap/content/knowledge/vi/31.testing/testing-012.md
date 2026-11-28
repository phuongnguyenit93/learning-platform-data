# Kiểm thử giao dịch bù trừ và cập nhật đồng thời

Ứng dụng dùng **Spring Data LDAP** có thể thực hiện nhiều thay đổi liên quan trong directory và các hệ thống khác: tạo entry người dùng, thêm group membership, cấp tài khoản trên identity provider hoặc cập nhật dữ liệu nghiệp vụ. Khi một bước thất bại sau khi bước trước đã thành công, ứng dụng cần chạy hành động bù trừ (compensation). Khi nhiều request cùng cập nhật một entry hoặc một tập giá trị, ứng dụng còn phải tránh ghi đè thay đổi của nhau.

Hai nhóm lỗi này thường không xuất hiện trong happy path. Chúng chỉ lộ ra khi network timeout, worker crash, request bị gửi lặp, hai thread cùng đọc/ghi hoặc directory replica chưa hội tụ. Vì vậy, kiểm thử cần chủ động tạo lỗi ở từng ranh giới, quan sát trạng thái LDAP thực tế và xác minh rằng compensation chỉ hoàn tác phần thay đổi do đúng workflow sở hữu.

Bài học hướng dẫn xây dựng test strategy cho **giao dịch bù trừ và cập nhật đồng thời** với Spring Data LDAP: kiểm thử unit cho orchestration, integration test với LDAP thật, failure injection, idempotency, race condition, optimistic concurrency, replica lag và kiểm tra sau compensation.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt transaction cục bộ của Spring với workflow nhiều hệ thống cần compensation.
- Xây dựng test fixture LDAP cô lập và dọn dữ liệu sau mỗi test.
- Kiểm thử compensation khi một bước provisioning thất bại.
- Xác minh compensation không xóa entry hoặc membership đã tồn tại trước workflow.
- Kiểm thử retry, duplicate request và timeout sau khi server đã thực hiện thao tác.
- Phân biệt cập nhật attribute nguyên tử trên một entry với read-modify-write có race condition.
- Tạo kiểm thử đồng thời có thể tái lập bằng `CountDownLatch` hoặc barrier.
- Kiểm thử optimistic locking, LDAP Assertion Control và conflict handling khi server hỗ trợ.
- Kiểm thử consistency khi đọc từ replica trễ.
- Thiết kế test matrix, quan sát kết quả và tránh test flaky.

## 2. Ranh giới cần kiểm thử

Khi phối hợp Spring Data LDAP với SQL, REST service và message broker, không có một `@Transactional` thông thường tự động rollback tất cả resource.

Ví dụ:

```java
@Transactional
public void onboard(Employee employee) {
    employeeRepository.save(employee);
    personRepository.save(toLdapPerson(employee));
    identityClient.createAccount(employee);
}
```

Nếu LDAP đã ghi entry rồi REST call thất bại, rollback database không tự xóa entry LDAP. Test chỉ kiểm tra transaction database rollback sẽ bỏ sót side effect này.

### 2.1. Phân biệt ba loại transaction

| Phạm vi | Cơ chế | Cách kiểm thử |
| --- | --- | --- |
| Một database transaction | Spring transaction manager/JDBC/JPA | Kiểm tra commit/rollback trên database. |
| Một LDAP Modify request | LDAP protocol áp dụng các modification cho một entry | Kiểm tra toàn bộ thay đổi của entry sau success/failure. |
| Một workflow nhiều hệ thống | Saga, compensation và reconciliation | Kiểm tra từng bước, trạng thái bền vững, retry và hành động bù trừ. |

LDAP Modify request có semantics nguyên tử trong phạm vi một entry theo giao thức; điều đó không tạo transaction chung giữa nhiều DN, nhiều LDAP server hoặc LDAP với database/HTTP. Không thiết kế test như thể nhiều lần gọi `modifyAttributes` được commit/rollback cùng nhau.

### 2.2. Bảng các bất biến cần bảo vệ

Trước khi viết test, xác định invariant của nghiệp vụ:

| Invariant | Ví dụ |
| --- | --- |
| Không tạo trùng identity | Một `employeeId` chỉ ánh xạ tới một entry provisioning đang hoạt động. |
| Không xóa tài nguyên có trước | Membership đã tồn tại trước workflow phải còn sau compensation. |
| Không mất cập nhật đồng thời | Hai request thêm hai member khác nhau thì cả hai member phải còn. |
| Không đánh dấu hoàn tất sớm | Workflow chỉ `COMPLETED` khi các bước bắt buộc đã được xác minh. |
| Retry an toàn | Cùng operation ID chạy lại không tạo thêm account hoặc membership. |
| Compensation có ownership | Chỉ hoàn tác side effect mà workflow hiện tại đã tạo. |
| Không kết luận sai do replica lag | Read từ replica stale không kích hoạt xóa hoặc tạo lại dữ liệu mù quáng. |
| Có thể tiếp tục sau crash | Worker mới tiếp tục từ trạng thái bền vững và xác minh side effect chưa được ghi nhận. |

Test nên kiểm tra invariant, không chỉ kiểm tra một method đã được gọi.

## 3. Chiến lược kiểm thử theo tầng

Một chiến lược cân bằng có nhiều tầng:

| Tầng | Phụ thuộc | Nội dung |
| --- | --- | --- |
| Unit test | JUnit, Mockito/fake | Quyết định bước tiếp theo, retry policy, compensation order và state transition. |
| LDAP adapter test | LDAP test server | DN, schema, attribute, add/remove/replace và result code. |
| Workflow integration test | Workflow DB + LDAP test server + stub HTTP | Side effect thật ở LDAP, state bền vững và compensation. |
| Concurrency test | Một LDAP server dùng chung cho nhiều client | Race condition, lost update, duplicate add và conflict. |
| Contract test | Stub/server test theo API đối tác | Idempotency key, timeout semantics và lỗi nghiệp vụ. |
| Resilience test | Fault injection/proxy hoặc stub điều khiển được | Mất response, connection reset, retry và recovery. |

Không cần chạy toàn bộ ma trận trên mọi commit. Unit test nên chạy thường xuyên; integration/concurrency suite có thể chạy trong pipeline phù hợp hoặc trước release.

### 3.1. Unit test không chứng minh semantics của LDAP

Mockito có thể xác minh service gọi `modifyAttributes`, nhưng không chứng minh:

- Server chấp nhận object class và attribute theo schema.
- `ADD_ATTRIBUTE` trả lỗi gì khi giá trị đã tồn tại.
- `REMOVE_ATTRIBUTE` có bị schema từ chối khi xóa giá trị cuối cùng không.
- DN equality được xử lý đúng.
- LDAP Modify request có atomic behavior như mong đợi.
- JNDI provider và server thực tế có cùng behavior với fake.

Vì vậy, các invariant liên quan đến directory phải có integration test.

## 4. Tạo LDAP test environment cô lập

Integration test nên kết nối tới directory dùng riêng cho test. Có thể dùng:

- OpenLDAP chạy trong container.
- ApacheDS hoặc embedded LDAP server phù hợp với dependency đang dùng.
- Directory test chuyên dụng đã reset dữ liệu theo mỗi test run.

Chọn server gần với môi trường production. Nếu production dùng Active Directory và test chỉ chạy OpenLDAP, cần có bộ kiểm thử bổ sung cho các semantics riêng của AD như ranged retrieval, matching rule và control.

### 4.1. Dependency test

Ví dụ với Gradle:

```groovy
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.testcontainers:junit-jupiter")
}
```

Đây là dependency test chung. Thêm module/container LDAP tương ứng với image và phiên bản server mà dự án chọn; không giả định một image hoặc embedded server thay thế được mọi vendor.

### 4.2. Tách cấu hình test khỏi production

Dùng profile riêng:

```yaml
spring:
  ldap:
    urls: ldap://localhost:1389
    base: dc=example,dc=org
    username: cn=admin,dc=example,dc=org
    password: test-only-password

app:
  provisioning:
    retry:
      max-attempts: 2
```

Thông tin trên chỉ dùng trong môi trường test cô lập. Không dùng credential này trên directory thật. Với Testcontainers, port thường được cấp động; nên lấy endpoint từ container runtime rồi inject vào cấu hình test thay vì cố định port nếu nhiều test run có thể chạy song song.

### 4.3. Seed dữ liệu có định danh riêng

Fixture nên dùng một base DN riêng, ví dụ:

```ldif
dn: ou=testing,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: testing

dn: ou=people,ou=testing,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: people

dn: ou=groups,ou=testing,dc=example,dc=org
objectClass: top
objectClass: organizationalUnit
ou: groups
```

Tạo entry người dùng và group trong phạm vi này. Mỗi test nên có suffix hoặc employee ID riêng để không xung đột khi chạy song song.

### 4.4. Dọn dữ liệu sau test

`@Transactional` trên test không tự rollback thay đổi LDAP. Dọn entry bằng `LdapTemplate.unbind(...)` hoặc helper xóa test fixture theo DN. Nếu entry có con, xóa child trước parent hoặc dùng helper recursive được giới hạn trong base DN test.

Không dùng thao tác cleanup rộng trên base DN dùng chung. Cleanup cần kiểm tra DN nằm trong namespace test và chỉ xóa entry do test tạo.

Ví dụ:

```java
import javax.naming.Name;
import org.springframework.ldap.core.LdapTemplate;

final class LdapFixtureCleaner {
    private final LdapTemplate ldapTemplate;

    LdapFixtureCleaner(LdapTemplate ldapTemplate) {
        this.ldapTemplate = ldapTemplate;
    }

    void deleteLeaf(Name dn) {
        ldapTemplate.unbind(dn);
    }
}
```

Ví dụ chỉ xóa một leaf entry. Với cây fixture, hãy lưu danh sách DN đã tạo và dọn theo thứ tự child-first. Tránh dựa vào wildcard DN hoặc search toàn directory để xóa dữ liệu test.

## 5. Thiết kế workflow testable

Tách coordinator khỏi adapter giúp mô phỏng lỗi mà không cần giả lập LDAP ở mọi test.

Một cấu trúc có thể gồm:

- `ProvisioningCoordinator`: điều phối workflow.
- `DirectoryProvisioningPort`: tạo, cập nhật, kích hoạt và bù trừ entry LDAP.
- `IdentityProviderPort`: tạo/disable tài khoản ngoài.
- `WorkflowStore`: lưu operation ID, trạng thái và step đã hoàn tất.
- `CompensationWorker`: tiếp tục các hành động bù trừ.

Coordinator chỉ nên quyết định trạng thái và thứ tự bước. Adapter chịu trách nhiệm idempotency và xác minh kết quả trên hệ thống đích.

### 5.1. Unit test bằng failure injection

Ví dụ: directory đã tạo pending entry, identity provider thất bại vĩnh viễn. Coordinator phải chuyển workflow sang trạng thái compensation:

```java
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.*;

import java.util.UUID;
import org.junit.jupiter.api.Test;

class ProvisioningCoordinatorTest {
    @Test
    void startsCompensationWhenIdentityProvisioningFailsPermanently() {
        WorkflowStore store = mock(WorkflowStore.class);
        DirectoryProvisioningPort directory =
                mock(DirectoryProvisioningPort.class);
        IdentityProviderPort identity =
                mock(IdentityProviderPort.class);
        MailboxPort mailbox = mock(MailboxPort.class);
        GroupMembershipPort groups = mock(GroupMembershipPort.class);

        UUID operationId = UUID.randomUUID();
        ProvisioningWorkflow workflow =
                ProvisioningWorkflow.requested(operationId, testIdentity());

        when(store.claim(operationId, "worker-1")).thenReturn(workflow);
        doThrow(new PermanentProvisioningException("ACCOUNT_REJECTED"))
                .when(identity)
                .provision(operationId, workflow.identity());

        ProvisioningCoordinator coordinator =
                new ProvisioningCoordinator(
                        store, directory, identity, mailbox, groups);

        assertThrows(
                PermanentProvisioningException.class,
                () -> coordinator.execute(operationId, "worker-1"));

        verify(directory).createPending(operationId, workflow.identity());
        verify(store).markDirectoryPending(operationId);
        verify(store).markCompensating(operationId, "ACCOUNT_REJECTED");
        verify(mailbox, never()).provision(any(), any());
        verify(groups, never()).assignRequiredGroups(any(), any());
        verify(store, never()).markCompleted(operationId);
    }

    private EmployeeIdentity testIdentity() {
        return new EmployeeIdentity("E-10042", "Alice Nguyen");
    }
}
```

`ProvisioningWorkflow`, `EmployeeIdentity` và exception trong ví dụ là kiểu dữ liệu của ứng dụng. Test xác minh coordinator dừng đúng bước và ghi trạng thái compensation; nó chưa chứng minh entry LDAP thật đã được xử lý bù trừ.

### 5.2. Kiểm thử thứ tự compensation

Nếu các bước tạo theo thứ tự LDAP → identity provider → mailbox → group membership, compensation thường cần xử lý các dependency theo chiều ngược. Tuy nhiên, thứ tự thực tế phụ thuộc chính sách và ownership.

Dùng `InOrder` để kiểm tra khi thứ tự là một invariant:

```java
import static org.mockito.Mockito.*;
import org.mockito.InOrder;

InOrder order = inOrder(groups, mailbox, identity, directory);

compensationWorker.compensate(operationId);

order.verify(groups).removeGroupsAddedBy(operationId, "E-10042");
order.verify(mailbox).disableIfProvisionedBy(operationId, "E-10042");
order.verify(identity).disableIfProvisionedBy(operationId, "E-10042");
order.verify(directory).quarantineIfOwned(operationId, "E-10042");
```

Chỉ kiểm tra thứ tự khi nghiệp vụ thực sự yêu cầu. Một số compensation có thể chạy độc lập hoặc song song; không ép mọi workflow vào một thứ tự cố định nếu không có dependency.

## 6. Kiểm thử compensation không xóa dữ liệu có trước

Đây là một trong những test quan trọng nhất khi cập nhật LDAP. Compensation phải biết workflow đã tạo thay đổi nào.

Ví dụ group `cn=engineering` đã có Alice trước khi workflow bắt đầu. Workflow mới yêu cầu thêm Alice nhưng thực tế membership đã tồn tại. Nếu một bước sau thất bại, compensation không được xóa membership có trước đó.

### 6.1. Lưu ownership của từng thay đổi

Khi add membership:

1. Đọc trạng thái hiện tại.
2. Nếu member đã có, ghi nhận `addedByOperation=false`.
3. Nếu chưa có, gửi `ADD_ATTRIBUTE`.
4. Nếu server trả duplicate do race, đọc lại và ghi nhận workflow không sở hữu thay đổi đó.
5. Chỉ ghi nhận `addedByOperation=true` khi thao tác add của workflow đã thành công.

Bản ghi workflow có thể lưu:

| Trường | Ví dụ |
| --- | --- |
| `operationId` | ID của saga. |
| `groupDn` | DN của group được cập nhật. |
| `memberDn` | DN của người dùng. |
| `addedByOperation` | Workflow có tạo membership này hay không. |
| `stepState` | `APPLIED`, `SKIPPED_EXISTING`, `COMPENSATED`. |

### 6.2. Test compensation giữ membership có trước

```java
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.Set;
import javax.naming.Name;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class MembershipCompensationIT {
    @Autowired GroupMembershipService membershipService;
    @Autowired MembershipCompensation compensation;

    @Test
    void doesNotRemoveMembershipThatExistedBeforeOperation() {
        Name groupDn = testGroupDn("preexisting");
        Name memberDn = testMemberDn("alice");
        membershipService.createGroupWithMember(groupDn, memberDn);

        MembershipChange change =
                membershipService.ensureMember(groupDn, memberDn);

        assertTrue(!change.addedByOperation());

        compensation.compensate(change);

        Set<Name> actual = membershipService.readMembers(groupDn);
        assertTrue(actual.contains(memberDn));
    }
}
```

Test này cần fixture directory thật. `ensureMember` trả ownership result; compensation chỉ remove nếu `addedByOperation=true`.

### 6.3. Test compensation chỉ xóa membership do workflow thêm

```java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Test
void removesMembershipCreatedByThisOperation() {
    Name groupDn = testGroupDn("new-member");
    Name memberDn = testMemberDn("bob");
    membershipService.createGroupWithAnotherMember(groupDn);

    MembershipChange change =
            membershipService.ensureMember(groupDn, memberDn);
    assertTrue(change.addedByOperation());

    compensation.compensate(change);

    assertFalse(
            membershipService.readMembers(groupDn).contains(memberDn));
}
```

Không xóa thành viên cuối cùng nếu object class yêu cầu tối thiểu một giá trị `member` hoặc `uniqueMember`. Fixture nên có một member nền để test chỉ xóa member do operation thêm.

## 7. Kiểm thử idempotency và retry

Một workflow có thể chạy lại sau crash hoặc message delivery lặp. Test cần xác minh cùng operation ID không tạo thêm side effect.

### 7.1. Chạy cùng command hai lần

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

@Test
void repeatedProvisioningCommandCreatesOneDirectoryEntry() {
    UUID operationId = UUID.randomUUID();
    workflowStore.insertRequested(
            operationId, new EmployeeIdentity("E-10042", "Alice Nguyen"));

    coordinator.execute(operationId, "worker-1");
    coordinator.execute(operationId, "worker-2");

    assertEquals(
            1,
            directoryTestSupport.countByOperationId(operationId));
}
```

Đây là integration-level assertion: đếm entry thực tế theo operation ID. Không chỉ verify mock `createPending` được gọi một lần, vì adapter có thể được gọi lại nhưng phải xử lý idempotently.

### 7.2. Timeout sau khi LDAP đã commit

Mô phỏng tình huống:

1. Adapter gửi create.
2. LDAP server ghi entry thành công.
3. Adapter giả lập mất response và ném timeout.
4. Workflow retry.
5. Adapter đọc lại entry theo business key/operation ID.
6. Workflow nhận ra thao tác đã thành công và tiếp tục.

Test phải xác minh không có entry trùng và state cuối cùng là đúng. Có thể dùng decorator/fake adapter để ném timeout sau khi delegate thực hiện thao tác thật:

```java
public final class CommitThenTimeoutDirectoryPort
        implements DirectoryProvisioningPort {
    private final DirectoryProvisioningPort delegate;
    private boolean failAfterFirstCreate = true;

    public CommitThenTimeoutDirectoryPort(
            DirectoryProvisioningPort delegate) {
        this.delegate = delegate;
    }

    @Override
    public void createPending(
            UUID operationId, EmployeeIdentity identity) {
        delegate.createPending(operationId, identity);
        if (failAfterFirstCreate) {
            failAfterFirstCreate = false;
            throw new TransientProvisioningException("RESPONSE_LOST");
        }
    }

    @Override
    public void activate(UUID operationId, String employeeId) {
        delegate.activate(operationId, employeeId);
    }

    @Override
    public void quarantineIfOwned(UUID operationId, String employeeId) {
        delegate.quarantineIfOwned(operationId, employeeId);
    }

    @Override
    public boolean isPendingCreatedBy(
            UUID operationId, String employeeId) {
        return delegate.isPendingCreatedBy(operationId, employeeId);
    }
}
```

Ví dụ decorator chỉ minh họa failure injection; state `failAfterFirstCreate` cần được bảo vệ nếu test gọi từ nhiều thread. Production adapter không nên dựa vào biến trong bộ nhớ để bảo đảm idempotency.

### 7.3. Phân loại retry

| Lỗi | Kết quả mong đợi |
| --- | --- |
| Connection reset trước khi request tới server | Retry theo backoff. |
| Timeout sau khi server đã commit | Đọc trạng thái rồi mới retry. |
| `entryAlreadyExists` và operation ID khớp | Coi là đã đạt trạng thái mong muốn. |
| `entryAlreadyExists` nhưng owner khác | Conflict/manual review. |
| `objectClassViolation` | Không retry mù; báo lỗi schema/dữ liệu. |
| Insufficient access rights | Không retry liên tục; cảnh báo quyền. |
| Server busy/unavailable | Retry có giới hạn. |
| Compensation timeout | Ghi compensation pending và retry riêng. |

Không gom mọi `NamingException` vào một retry policy. Adapter cần phân loại LDAP result code và nguyên nhân transport.

## 8. Kiểm thử cập nhật đồng thời

Concurrent update có thể gây:

- Lost update khi hai writer cùng replace toàn bộ tập attribute.
- Duplicate operation khi hai worker cùng tạo entry.
- Compensation xóa nhầm thay đổi của workflow khác.
- State transition bị worker cũ ghi đè.
- Search trả kết quả stale do replication.

Test phải tạo overlap thực sự giữa các thao tác. Chỉ chạy hai test tuần tự không thể chứng minh xử lý đồng thời.

### 8.1. Phân biệt ADD với read-modify-write

Giả sử một group có member A. Hai worker muốn thêm B và C.

**Cách có nguy cơ mất cập nhật:**

1. Worker 1 đọc `{A}`.
2. Worker 2 đọc `{A}`.
3. Worker 1 replace thành `{A, B}`.
4. Worker 2 replace thành `{A, C}`.

Kết quả cuối có thể là `{A, C}`; member B bị mất.

**Cách phù hợp hơn khi chỉ thêm từng giá trị:** mỗi worker gửi `ADD_ATTRIBUTE` cho đúng member của mình. LDAP server xử lý từng Modify request trên entry; hai giá trị khác nhau có thể được giữ lại mà không cần client replace snapshot cũ.

### 8.2. Integration test hai writer thêm hai member khác nhau

```java
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import javax.naming.Name;
import org.junit.jupiter.api.Test;

class ConcurrentMembershipIT {
    @Test
    void concurrentAddsKeepBothDifferentMembers() throws Exception {
        Name groupDn = testGroupDn("concurrent-add");
        Name memberB = testMemberDn("bob");
        Name memberC = testMemberDn("carol");
        membershipService.createGroupWithAnotherMember(groupDn);

        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch start = new CountDownLatch(1);
        ExecutorService pool = Executors.newFixedThreadPool(2);

        try {
            Future<?> first = pool.submit(() -> {
                ready.countDown();
                start.await();
                membershipService.addMember(groupDn, memberB);
                return null;
            });

            Future<?> second = pool.submit(() -> {
                ready.countDown();
                start.await();
                membershipService.addMember(groupDn, memberC);
                return null;
            });

            assertTrue(ready.await(5, TimeUnit.SECONDS));
            start.countDown();
            first.get(10, TimeUnit.SECONDS);
            second.get(10, TimeUnit.SECONDS);

            var actual = membershipService.readMembers(groupDn);
            assertTrue(actual.contains(memberB));
            assertTrue(actual.contains(memberC));
        } finally {
            pool.shutdownNow();
        }
    }
}
```

Đoạn test giả định `membershipService.addMember` gửi `ADD_ATTRIBUTE` cho một giá trị, không đọc rồi replace toàn bộ collection. `CountDownLatch` tạo điểm bắt đầu chung để tăng khả năng hai thao tác overlap; không dùng `Thread.sleep` để cố tạo race.

Nếu test chạy song song với test khác, mỗi test phải dùng group DN riêng. Cần đặt timeout cho `ready.await()`/`Future.get()` trong suite thực tế để test không treo vô hạn.

### 8.3. Test phát hiện lost update

Để chứng minh một implementation read-modify-write không an toàn, chèn barrier ngay sau khi cả hai worker đã đọc cùng snapshot:

```java
Set<Name> snapshot = membershipService.readMembers(groupDn);
bothReadersReady.countDown();
allowWriters.await();

Set<Name> replacement = new HashSet<>(snapshot);
replacement.add(myMember);
membershipService.replaceMembers(groupDn, replacement);
```

Test điều khiển hai worker cùng đọc `{A}`, sau đó cho lần lượt replace `{A, B}` và `{A, C}`. Cuối test, nếu chỉ còn một trong hai member mới, test đã tái hiện lost update.

Test kiểu này có ích khi kiểm chứng một implementation cũ hoặc regression. Sau khi chuyển sang `ADD_ATTRIBUTE` hoặc concurrency control, test acceptance phải xác minh cả B và C đều tồn tại.

## 9. Kiểm thử cập nhật cùng một giá trị

Hai worker có thể đồng thời thêm cùng một member:

- Worker đầu tiên add thành công.
- Worker thứ hai có thể nhận LDAP result `attributeOrValueExists`.

Đây không nhất thiết là lỗi nghiệp vụ. Adapter cần đọc lại entry và xác minh member đã tồn tại; nếu đúng, trả kết quả idempotent. Nếu lỗi thuộc attribute khác hoặc DN khác, không được bỏ qua.

Test cần xác minh:

1. Chỉ có một giá trị member trong directory.
2. Cả hai workflow đều nhận kết quả cuối là member đã tồn tại.
3. Ownership được ghi chính xác: workflow thực sự add thành công mới sở hữu side effect; workflow gặp duplicate không được tự nhận ownership.
4. Compensation của workflow thứ hai không xóa member do workflow thứ nhất thêm.

### 9.1. Ví dụ kiểm tra duplicate add

```java
@Test
void concurrentDuplicateAddsDoNotCreateDuplicateMembership() throws Exception {
    Name groupDn = testGroupDn("duplicate-add");
    Name memberDn = testMemberDn("alice");
    membershipService.createGroupWithAnotherMember(groupDn);

    runConcurrently(
            () -> membershipService.ensureMember(groupDn, memberDn),
            () -> membershipService.ensureMember(groupDn, memberDn));

    var members = membershipService.readMembers(groupDn);
    assertEquals(1, members.stream()
            .filter(memberDn::equals)
            .count());
}
```

Helper `runConcurrently` cần đồng bộ start bằng latch và lấy kết quả của cả hai future. Với LDAP attribute semantics, giá trị trùng không được lưu như hai phần tử độc lập; nhưng response của request thứ hai vẫn có thể là duplicate-value error.

## 10. Kiểm thử optimistic concurrency

Nếu ứng dụng lưu workflow state trong SQL, dùng version để ngăn worker cũ ghi đè state mới. Test cần có hai transaction cùng đọc một version:

1. Worker A đọc version 4.
2. Worker B đọc version 4.
3. Worker A cập nhật state và version thành 5.
4. Worker B cập nhật với expected version 4.
5. Update của B phải thất bại vì không còn version phù hợp.

Ví dụ SQL:

```sql
UPDATE provisioning_workflow
SET state = :newState,
    version = version + 1
WHERE operation_id = :operationId
  AND version = :expectedVersion;
```

Test assert đúng một worker update thành công và worker còn lại phải reload state hoặc chuyển conflict handling. Không để worker B tiếp tục side effect LDAP dựa trên snapshot cũ.

### 10.1. LDAP Assertion Control

LDAP Assertion Control (RFC 4528) cho phép client yêu cầu server chỉ thực hiện operation nếu một filter assertion vẫn đúng tại thời điểm xử lý. Server phải hỗ trợ control này; client cũng cần gửi control đúng cách.

Ví dụ điều kiện khái niệm:

`(&(employeeId=E-10042)(appVersion=7))`

Chỉ update entry khi employee ID và version vẫn khớp. Nếu một writer khác đã tăng version, server trả lỗi assertion failed thay vì âm thầm ghi đè.

Không giả định mọi directory hỗ trợ Assertion Control hoặc `LdapTemplate` tự bật control. Khi dùng control, test cần:

- Kiểm tra Root DSE/capability hoặc tài liệu server để xác nhận support.
- Gửi control qua API phù hợp với provider.
- Xác minh request thành công khi assertion đúng.
- Xác minh request thất bại và dữ liệu không đổi khi assertion sai.
- Kiểm tra behavior trên đúng vendor/version production.

Nếu server không hỗ trợ, dùng coordinator/lock hoặc giảm số writer cùng sở hữu dữ liệu.

## 11. Kiểm thử nhiều LDAP operation và giới hạn atomicity

Một LDAP Modify request có thể gồm nhiều `ModificationItem`. Nếu request thất bại do schema hoặc constraint, test nên xác minh server không để entry ở trạng thái chỉ áp dụng một phần các modification trong request.

Ví dụ request cùng cập nhật hai attribute:

```java
ModificationItem[] changes = {
    new ModificationItem(
            DirContext.REPLACE_ATTRIBUTE,
            new BasicAttribute("appProvisioningState", "active")),
    new ModificationItem(
            DirContext.ADD_ATTRIBUTE,
            new BasicAttribute("appProvisioningOperationId", operationId))
};

ldapTemplate.modifyAttributes(personDn, changes);
```

Đây là một request trên một entry. Nếu ứng dụng gọi hai lần `modifyAttributes` trên hai DN, hai request đó không tạo một transaction chung.

### 11.1. Test atomicity trong một entry

Thiết kế fixture sao cho modification thứ hai vi phạm schema hoặc constraint. Gửi một Modify request chứa cả hai thay đổi, sau đó đọc lại entry và xác minh thay đổi đầu tiên cũng không bị áp dụng nếu server tuân thủ atomic semantics của LDAP Modify.

Không dùng một fixture gây lỗi không xác định; hãy chọn constraint đã biết trên directory test và kiểm tra result code cụ thể theo server.

### 11.2. Test workflow nhiều entry

Nếu workflow cập nhật group A rồi group B:

- Cho A thành công.
- Làm B thất bại.
- Xác minh workflow state ghi nhận A đã hoàn tất.
- Chạy compensation cho A theo ownership.
- Xác minh B không bị đánh dấu thành công.
- Chạy lại workflow và xác minh không tạo side effect trùng.

Đây là test saga, không phải test LDAP transaction.

## 12. Kiểm thử replication lag và consistency

Trong topology có nhiều LDAP node, một write thành công trên writer không bảo đảm replica đọc thấy ngay.

Test cần phân biệt:

- Writer chưa commit.
- Writer commit nhưng response bị mất.
- Writer commit và replica chưa replicate.
- Replica đã replicate nhưng client đang đọc nhầm search base/endpoint.
- ACL hoặc referral khiến search không trả entry.

### 12.1. Không dùng sleep để đợi replication

Thay vì `Thread.sleep(5000)` cố định, dùng polling có deadline và điều kiện rõ ràng:

```java
public void awaitVisible(
        Name dn,
        Duration timeout,
        Duration interval) {

    Instant deadline = Instant.now().plus(timeout);
    while (Instant.now().isBefore(deadline)) {
        if (directoryReader.exists(dn)) {
            return;
        }
        try {
            Thread.sleep(interval.toMillis());
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(ex);
        }
    }
    throw new AssertionError("Entry did not become visible before deadline");
}
```

Đây là polling có deadline, không phải bảo đảm replication. Trong test thực tế, `exists` cần đọc đúng replica cần kiểm tra; interval/timeout phải phù hợp môi trường. Với test unit, thay clock/scheduler bằng abstraction để không chờ thời gian thật.

### 12.2. Kiểm thử không compensation nhầm do replica stale

1. Tạo entry trên writer.
2. Làm read replica trả kết quả stale hoặc dùng stub reader mô phỏng lag.
3. Chạy reconciliation.
4. Xác minh workflow chuyển `VERIFY_PENDING`/retry thay vì xóa hoặc tạo lại entry.
5. Cho replica thấy entry.
6. Chạy lại reconciliation và xác minh workflow hoàn tất.

Không cần ép một LDAP test container đơn lẻ mô phỏng replication. Có thể kiểm thử logic workflow bằng fake replica reader, sau đó có bộ test topology thật nếu production yêu cầu bảo đảm vendor-specific.

## 13. Kiểm thử outbox, inbox và duplicate event

Nếu workflow ghi trạng thái và event vào outbox cùng một database transaction, test cần xác minh:

- Khi transaction rollback, cả workflow update và outbox row đều không tồn tại.
- Khi transaction commit, cả hai cùng tồn tại.
- Publisher crash sau khi gửi nhưng trước khi mark sent có thể gửi event lại.
- Consumer dedupe theo event ID và chỉ áp dụng business change một lần.

### 13.1. Test consumer nhận event trùng

```java
@Test
void duplicateEventIsAppliedOnlyOnce() {
    UUID eventId = UUID.randomUUID();
    ProvisioningCompleted event =
            new ProvisioningCompleted(eventId, "E-10042");

    consumer.handle(event);
    consumer.handle(event);

    assertEquals(1, inboxRepository.countByEventId(eventId));
    assertEquals(1, downstreamProjection.countFor("E-10042"));
}
```

Hai lần gọi consumer phải tạo cùng kết quả cuối như một lần gọi. Nếu consumer gọi LDAP, test phải xác minh trạng thái LDAP cuối cùng thay vì chỉ đếm số lần mock được gọi.

## 14. Kiểm thử Spring transaction không rollback LDAP

Một test dễ gây hiểu nhầm là:

```java
@Test
@Transactional
void databaseRollbackDoesNotUndoLdapWrite() {
    // Ghi một entry LDAP.
    // Gây lỗi để transaction database rollback.
}
```

Khi test method kết thúc, transaction manager có thể rollback database test data nhưng LDAP entry vẫn tồn tại. Vì thế:

- Cleanup LDAP phải tường minh.
- Không dựa vào `@Rollback` để xóa LDAP fixture.
- Nếu test dùng nhiều transaction manager, khai báo rõ manager được áp dụng.
- Kiểm tra cả database và directory sau failure.

Một test tốt chứng minh rằng workflow gọi compensation hoặc reconciliation để xử lý LDAP side effect, chứ không kỳ vọng database rollback tự làm điều đó.

## 15. Tránh test flaky và race không tái lập

Concurrency test thường thất bại ngẫu nhiên nếu thiếu điều khiển thời điểm.

Thực hành:

- Dùng `CountDownLatch`, `CyclicBarrier` hoặc test hook để đồng bộ điểm bắt đầu.
- Không dựa vào `Thread.sleep` để tạo race.
- Đặt timeout cho mọi `await`, `Future.get` và test method.
- Dùng DN/operation ID riêng cho từng test.
- Dùng một LDAP server ổn định trong cùng test run; tránh restart server khi worker còn hoạt động.
- Đóng executor trong `finally`.
- Đọc lại trạng thái directory sau khi tất cả future hoàn tất.
- Chạy lặp concurrency test nhiều lần trong pipeline phù hợp để phát hiện race hiếm.
- Ghi lại operation ID và DN test khi thất bại, nhưng không log secret.

Nếu test chỉ thất bại khi chạy song song với test khác, kiểm tra fixture dùng chung, cleanup quá rộng và shared mutable state trong test support.

## 16. Ma trận kiểm thử đầy đủ

| Nhóm | Trường hợp | Kết quả mong đợi |
| --- | --- | --- |
| Compensation | Bước identity thất bại sau LDAP create | Workflow chuyển compensating và entry được quarantine/xóa theo ownership. |
| Compensation | Membership đã tồn tại trước workflow | Compensation không xóa membership đó. |
| Compensation | Membership do workflow thêm | Compensation chỉ xóa đúng membership đó. |
| Compensation | Compensation timeout | Trạng thái bù trừ được lưu và retry được. |
| Idempotency | Cùng operation ID chạy hai lần | Không tạo thêm entry/account/membership. |
| Idempotency | Timeout sau LDAP commit | Adapter đọc lại trạng thái trước khi retry. |
| Idempotency | Duplicate add cùng member | Một giá trị tồn tại; ownership chính xác. |
| Concurrency | Hai writer add hai member khác nhau | Cả hai member đều còn. |
| Concurrency | Hai writer add cùng member | Không có side effect trùng; duplicate được phân loại. |
| Concurrency | Hai writer replace cùng snapshot | Test phát hiện lost update. |
| Concurrency | Optimistic version cũ | Chỉ một update thành công. |
| LDAP protocol | Một Modify request có nhiều changes | Không có partial apply khi request bị từ chối theo semantics server. |
| Workflow | Bước LDAP A thành công, LDAP B thất bại | A được compensation hoặc workflow resume đúng. |
| Replication | Replica chưa thấy entry | Không kết luận write thất bại hoặc compensation nhầm. |
| Outbox | DB transaction rollback | Workflow và outbox cùng rollback. |
| Inbox | Event được giao hai lần | Consumer áp dụng nghiệp vụ một lần. |
| Cleanup | Test kết thúc | Chỉ fixture trong namespace test bị xóa. |

## 17. Quan sát kết quả và chẩn đoán

Khi một concurrency test thất bại, cần đủ dữ liệu để tái dựng lịch thực thi:

- Operation ID của mỗi workflow.
- DN của entry/group liên quan.
- Worker/thread ID.
- Thời điểm bắt đầu/kết thúc từng LDAP operation.
- LDAP result code và loại exception.
- Version/state trước và sau update.
- Ownership marker của side effect.
- Endpoint/replica được đọc hoặc ghi.
- Trạng thái outbox/inbox nếu có.

Không ghi password, bind credential, access token, private key hoặc binary payload. Dùng DN/employee ID giả lập trong test và che dữ liệu cá nhân trong log.

Các metric hữu ích:

| Metric | Điều cần phát hiện |
| --- | --- |
| Compensation success/failure | Side effect nào khó thu hồi. |
| Retry count theo LDAP result code | Lỗi tạm thời hay lỗi schema/quyền bị retry sai. |
| Duplicate operation count | Request/event lặp hoặc idempotency chưa đúng. |
| Optimistic lock conflict | Workflow đang bị nhiều worker xử lý. |
| LDAP modify latency | Directory chậm hoặc quá tải. |
| Reconciliation mismatch | Dữ liệu giữa các hệ thống đang lệch. |
| Replica visibility delay | Read-after-write chưa đạt yêu cầu. |

## 18. Lỗi kiểm thử thường gặp

| Cách kiểm thử sai | Vì sao không đủ | Cách cải thiện |
| --- | --- | --- |
| Chỉ verify `modifyAttributes` được gọi | Không biết server đã ghi đúng hay chưa. | Đọc lại entry từ LDAP test server. |
| Dùng `@Transactional` để rollback LDAP fixture | LDAP không tham gia transaction manager JDBC mặc định. | Cleanup LDAP tường minh. |
| Chỉ test happy path | Không phát hiện side effect dở dang. | Inject failure sau mỗi bước. |
| Compensation luôn unbind DN | Có thể xóa entry có trước hoặc do actor khác sở hữu. | Lưu ownership và kiểm tra trước khi xóa. |
| Retry mọi `NamingException` | Lặp cả lỗi schema/quyền/conflict. | Phân loại result code và transport failure. |
| Hai thread chạy gần nhau bằng sleep | Không tái lập được race. | Dùng latch/barrier tại điểm đọc/ghi. |
| Test replace tập membership nhưng không kiểm tra concurrent update | Bỏ sót lost update. | Cho hai worker cùng đọc snapshot rồi xác minh cả hai thay đổi. |
| Đọc từ một replica rồi kết luận dữ liệu mất | Có thể replication lag hoặc ACL. | Kiểm tra authoritative endpoint và trạng thái hội tụ. |
| Chỉ kiểm tra số lần mock được gọi | Không xác minh kết quả cuối trong directory. | Assert entry, attribute và workflow state thực tế. |
| Cleanup toàn OU dùng chung | Có thể xóa dữ liệu test khác hoặc dữ liệu ngoài test. | DN namespace riêng và cleanup theo danh sách fixture. |

## 19. Bài tập thực hành

**Bài 1.** LDAP đã tạo entry nhưng identity provider trả timeout. Test nên xác minh điều gì trước khi retry?

**Đáp án:** Đọc entry theo business key/operation ID và query trạng thái identity provider nếu API hỗ trợ idempotency key. Timeout không chứng minh thao tác chưa commit.

**Bài 2.** Một membership đã tồn tại trước workflow. Compensation có được remove member đó không?

**Đáp án:** Không. Workflow không sở hữu thay đổi này; cần lưu `addedByOperation=false` và giữ membership sau compensation.

**Bài 3.** Hai worker cùng đọc `{A}` rồi replace lần lượt `{A,B}` và `{A,C}`. Kết quả nào cho thấy lost update?

**Đáp án:** Tập cuối chỉ còn `{A,B}` hoặc `{A,C}` thay vì giữ cả B và C. Test cần đồng bộ hai worker sau khi đọc snapshot để tái hiện race.

**Bài 4.** Hai worker cùng add một member. Vì sao một worker có thể nhận `attributeOrValueExists`?

**Đáp án:** Worker còn lại đã add giá trị trước. Adapter cần đọc lại và coi là trạng thái đã đạt nếu đúng member/group; worker không thực sự tạo membership không được nhận ownership.

**Bài 5.** Một test có `@Transactional` rollback database nhưng LDAP entry vẫn còn. Đây có phải lỗi Spring không?

**Đáp án:** Không. LDAP là resource ngoài transaction manager JDBC thông thường. Test phải cleanup LDAP hoặc kiểm tra compensation riêng.

**Bài 6.** Vì sao cần test `ADD_ATTRIBUTE` và `REPLACE_ATTRIBUTE` riêng?

**Đáp án:** Add chỉ thêm giá trị cụ thể; replace thay toàn bộ tập. Replace dựa trên snapshot cũ có thể xóa cập nhật của writer khác.

**Bài 7.** Có thể dùng LDAP Assertion Control cho mọi server không?

**Đáp án:** Không. Cần xác minh server hỗ trợ control và client gửi đúng request control; test cả assertion đúng và sai trên đúng vendor/version.

**Bài 8.** Reconciliation đọc replica chưa thấy entry vừa ghi. Có nên chạy compensation xóa workflow không?

**Đáp án:** Không. Trước hết xác minh writer, ACL và replication lag; có thể chờ hội tụ rồi đọc lại.

## 20. Checklist trước khi merge

### Fixture và môi trường

- [ ] Test dùng LDAP server cô lập, không dùng directory production.
- [ ] Schema và object class test tương thích môi trường mục tiêu.
- [ ] DN/operation ID riêng cho từng test.
- [ ] Cleanup chỉ xóa fixture do test tạo.
- [ ] Binary/credential không xuất hiện trong log.

### Compensation và retry

- [ ] Test lỗi sau từng side effect.
- [ ] Test compensation của thay đổi do workflow tạo.
- [ ] Test bảo toàn dữ liệu có trước workflow.
- [ ] Test compensation retry và failure state.
- [ ] Test timeout sau commit và duplicate command.
- [ ] Test phân loại lỗi schema, quyền và lỗi tạm thời.

### Concurrency

- [ ] Test hai writer cập nhật hai giá trị khác nhau.
- [ ] Test duplicate add cùng giá trị.
- [ ] Test lost update với read-modify-write.
- [ ] Test optimistic version/Assertion Control nếu được sử dụng.
- [ ] Test worker cũ không ghi đè workflow state mới.
- [ ] Test dùng latch/barrier và timeout, không phụ thuộc sleep.

### Consistency và tích hợp

- [ ] Test read-after-write trên endpoint đúng vai trò.
- [ ] Test replica lag hoặc fake stale reader.
- [ ] Test outbox rollback cùng business transaction.
- [ ] Test consumer nhận event trùng.
- [ ] Test reconciliation không sửa/xóa khi chưa xác minh ownership.
- [ ] Test kết quả cuối trong LDAP, workflow DB và hệ thống downstream.

## 21. Ghi nhớ

- Transaction database, LDAP Modify request và workflow nhiều hệ thống có phạm vi nguyên tử khác nhau.
- Unit test kiểm tra quyết định orchestration; integration test phải xác minh dữ liệu thật trên LDAP test server.
- Compensation cần lưu ownership của từng side effect để không xóa membership hoặc entry có trước workflow.
- Timeout sau commit là kết quả chưa xác định; test phải xác minh trạng thái trước khi retry.
- `ADD_ATTRIBUTE` cho từng giá trị thường tránh lost update tốt hơn read-modify-write rồi replace toàn bộ collection.
- Dùng latch/barrier để tạo race condition tái lập; luôn đọc lại trạng thái cuối sau khi các worker kết thúc.
- Optimistic locking bảo vệ workflow store; LDAP Assertion Control chỉ dùng khi server hỗ trợ và đã được kiểm thử.
- Replica lag có thể tạo false mismatch; không chạy compensation chỉ dựa trên một lần đọc từ replica stale.
- `@Transactional` của JDBC không tự rollback side effect LDAP; cleanup và compensation phải được kiểm thử riêng.
- Test suite cần bao gồm compensation, retry, idempotency, duplicate event, concurrency, replication và cleanup.

## Tài liệu tham khảo

- [RFC 4511 — Lightweight Directory Access Protocol](https://www.rfc-editor.org/rfc/rfc4511.html): semantics của LDAP Modify request và result code.
- [RFC 4528 — LDAP Assertion Control](https://www.rfc-editor.org/rfc/rfc4528.html): điều kiện assertion cho cập nhật có kiểm soát đồng thời.
- [RFC 5805 — LDAP Transactions](https://www.rfc-editor.org/rfc/rfc5805.html): transaction extension tùy chọn của LDAP và giới hạn phạm vi.
- [Spring LDAP — Testing](https://docs.spring.io/spring-ldap/reference/testing.html): hỗ trợ kiểm thử Spring LDAP và test context.
- [Spring LDAP — LdapTemplate API](https://docs.spring.io/spring-ldap/reference/api/java/org/springframework/ldap/core/LdapTemplate.html): lookup, modify, bind và unbind.
- [Spring Framework — Testing](https://docs.spring.io/spring-framework/reference/testing.html): tích hợp Spring TestContext và quản lý test application context.
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/): test lifecycle, assertions và parallel execution.
- [Testcontainers for Java](https://java.testcontainers.org/): chạy service phụ thuộc trong container phục vụ integration test.
