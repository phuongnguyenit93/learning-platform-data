# Kiểm thử mô hình nghiệp vụ không cần Neo4j

## Mục tiêu

Sau bài học này, bạn có thể:

- Xác định quy tắc nghiệp vụ nào có thể kiểm thử trực tiếp bằng Java mà không khởi động Neo4j.
- Kiểm thử value object, aggregate và relationship có thuộc tính bằng JUnit.
- Kiểm tra các bất biến của mô hình graph như thành viên duy nhất, quyền sở hữu và quan hệ hợp lệ.
- Kiểm thử application service qua repository port bằng mock, stub hoặc fake.
- Làm cho test ổn định bằng cách kiểm soát thời gian và nguồn sinh định danh.
- Phân biệt unit test mô hình nghiệp vụ với kiểm thử mapping SDN, Cypher và transaction.
- Tránh biến unit test thành một bản mô phỏng database không đáng tin cậy.

## 1. Vì sao mô hình nghiệp vụ có thể được kiểm thử mà không cần Neo4j?

Spring Data Neo4j (SDN) cung cấp tầng persistence để ánh xạ domain object sang node, relationship và property. Nhưng các quy tắc như “một nhóm phải có ít nhất một owner”, “một thành viên không được tham gia hai lần” hoặc “chỉ owner mới được thêm thành viên” là quy tắc Java của ứng dụng.

Những quy tắc này không cần database để kiểm tra. Chúng có thể chạy trong bộ nhớ với object bình thường.

Một ứng dụng graph thường có thể chia thành các phần:

~~~text
Domain model
  - Value objects
  - Node concepts / aggregates
  - Relationship concepts
  - Business rules
        |
        v
Application service
  - Điều phối use case
  - Gọi repository port
  - Lấy thời gian / định danh qua dependency
        |
        v
Persistence adapter
  - Spring Data Neo4j repository
  - Neo4jTemplate / Neo4jClient
  - Mapping và Cypher
        |
        v
Neo4j database
~~~

Unit test cho domain model tập trung vào phần đầu. Test application service có thể thay persistence adapter bằng mock hoặc fake. Vì không có truy vấn Cypher hay mapping database nào được thực thi, test không cần Neo4j server, transaction manager hoặc Spring ApplicationContext.

Điều này không có nghĩa mọi test của ứng dụng Neo4j đều có thể bỏ database. Khi cần xác nhận label, relationship type, hướng relationship, property mapping, Cypher hoặc transaction thực sự hoạt động, phải có kiểm thử tích hợp phù hợp.

Ngay cả khi class đang kiểm thử có annotation `@Node` hoặc `@RelationshipProperties`, bạn vẫn có thể khởi tạo nó như object Java và gọi các method nghiệp vụ mà không cần Neo4j. Tuy nhiên, unit test đó chỉ kiểm tra hành vi Java; nó không xác nhận annotation được SDN diễn giải hoặc ánh xạ đúng.

## 2. Phân biệt các loại kiểm thử

| Loại test | Đối tượng | Cần Neo4j? | Ví dụ |
|---|---|---:|---|
| Unit test domain | Value object, aggregate, relationship rule | Không | Không cho phép xóa owner cuối cùng |
| Unit test application service | Use case và tương tác với repository port | Không | Thêm thành viên rồi lưu aggregate |
| Test mapper thuần | Hàm chuyển đổi Java tự viết | Không | Chuyển Membership sang persistence model |
| SDN mapping test | Mapping entity, relationship và property của SDN | Có | Xác nhận RelationshipProperties được lưu đúng |
| Repository/Cypher integration test | Query, projection, custom repository method | Có | Kiểm tra Query trả kết quả đúng |
| Transaction integration test | Commit, rollback và concurrency | Có | Hai thao tác ghi cùng tham gia transaction |

Hãy chọn loại test theo điều cần chứng minh. Nếu quy tắc chỉ là phép tính hoặc điều kiện trên object, unit test là đủ. Nếu câu hỏi liên quan đến cách SDN giao tiếp với Neo4j, unit test không thể chứng minh điều đó.

## 3. Mô hình ví dụ: Team và Membership

Giả sử ứng dụng quản lý các nhóm làm việc. Một Team là aggregate root; mỗi thành viên liên kết với nhóm thông qua một quan hệ Membership.

Quan hệ này có thuộc tính nghiệp vụ riêng:

- memberId: định danh thành viên.
- role: vai trò trong nhóm, chẳng hạn OWNER hoặc MEMBER.
- joinedAt: thời điểm tham gia.

Các quy tắc:

1. Tên nhóm không được rỗng và được trim khoảng trắng đầu/cuối.
2. Mỗi member chỉ có một Membership trong một Team.
3. Chỉ owner mới được thêm, đổi vai trò hoặc xóa thành viên.
4. Team phải luôn có ít nhất một owner.
5. Không thể hạ vai trò hoặc xóa owner cuối cùng.
6. Khi đổi vai trò, joinedAt của Membership được giữ nguyên.

Đây là các quy tắc của mô hình nghiệp vụ. Chúng không phụ thuộc vào việc quan hệ được lưu bằng @Relationship, @RelationshipProperties hay Cypher thủ công.

### Value object và relationship model

TeamId và MemberId bảo vệ định dạng định danh:

~~~java
public record TeamId(String value) {

    public TeamId {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                "Team ID must not be blank"
            );
        }
    }
}
~~~

~~~java
public record MemberId(String value) {

    public MemberId {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                "Member ID must not be blank"
            );
        }
    }
}
~~~

Vai trò:

~~~java
public enum TeamRole {
    OWNER,
    MEMBER
}
~~~

Membership biểu diễn một quan hệ có dữ liệu riêng:

~~~java
import java.time.Instant;
import java.util.Objects;

public record Membership(
    MemberId memberId,
    TeamRole role,
    Instant joinedAt
) {

    public Membership {
        Objects.requireNonNull(memberId, "memberId is required");
        Objects.requireNonNull(role, "role is required");
        Objects.requireNonNull(joinedAt, "joinedAt is required");
    }
}
~~~

Một test cho value object có thể kiểm tra dữ liệu bắt buộc và equality:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.time.Instant;
import org.junit.jupiter.api.Test;

class MembershipTest {

    @Test
    void keepsRelationshipProperties() {
        Instant joinedAt = Instant.parse("2026-01-10T09:00:00Z");

        Membership membership = new Membership(
            new MemberId("member-10"),
            TeamRole.MEMBER,
            joinedAt
        );

        assertThat(membership.memberId())
            .isEqualTo(new MemberId("member-10"));
        assertThat(membership.role()).isEqualTo(TeamRole.MEMBER);
        assertThat(membership.joinedAt()).isEqualTo(joinedAt);
    }

    @Test
    void requiresMemberEndpointAndRelationshipProperties() {
        assertThatThrownBy(() ->
            new Membership(
                null,
                TeamRole.MEMBER,
                Instant.parse("2026-01-10T09:00:00Z")
            )
        ).isInstanceOf(NullPointerException.class);
    }
}
~~~

Test này chạy hoàn toàn trong JVM. Nó kiểm tra ý nghĩa và tính hợp lệ của relationship model; không kiểm tra relationship được lưu với type hoặc direction nào trong Neo4j.

## 4. Đặt bất biến trong aggregate

Các quy tắc ảnh hưởng đến nhiều Membership nên được kiểm tra tại Team, thay vì để controller hoặc repository tự quyết định.

Ví dụ aggregate:

~~~java
import java.time.Instant;
import java.util.Collection;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;

public final class Team {

    private final TeamId id;
    private String name;
    private final Map<MemberId, Membership> memberships =
        new LinkedHashMap<>();

    public Team(
            TeamId id,
            String name,
            MemberId firstOwner,
            Instant createdAt
    ) {
        this.id = Objects.requireNonNull(id, "id is required");
        this.name = normalizeName(name);

        Membership ownerMembership = new Membership(
            firstOwner,
            TeamRole.OWNER,
            createdAt
        );

        memberships.put(firstOwner, ownerMembership);
    }

    public void addMember(
            MemberId actorId,
            MemberId newMemberId,
            Instant joinedAt
    ) {
        requireOwner(actorId);

        if (memberships.containsKey(newMemberId)) {
            throw new DomainRuleViolation(
                "Member already belongs to this team"
            );
        }

        memberships.put(
            newMemberId,
            new Membership(newMemberId, TeamRole.MEMBER, joinedAt)
        );
    }

    public void changeRole(
            MemberId actorId,
            MemberId targetId,
            TeamRole newRole
    ) {
        requireOwner(actorId);
        Objects.requireNonNull(newRole, "newRole is required");

        Membership current = membershipOf(targetId)
            .orElseThrow(() ->
                new DomainRuleViolation("Member does not belong to this team")
            );

        if (current.role() == newRole) {
            return;
        }

        if (current.role() == TeamRole.OWNER
                && newRole != TeamRole.OWNER
                && ownerCount() == 1) {
            throw new DomainRuleViolation(
                "A team must have at least one owner"
            );
        }

        memberships.put(
            targetId,
            new Membership(targetId, newRole, current.joinedAt())
        );
    }

    public void removeMember(MemberId actorId, MemberId targetId) {
        requireOwner(actorId);

        Membership target = membershipOf(targetId)
            .orElseThrow(() ->
                new DomainRuleViolation("Member does not belong to this team")
            );

        if (target.role() == TeamRole.OWNER && ownerCount() == 1) {
            throw new DomainRuleViolation(
                "The last owner cannot be removed"
            );
        }

        memberships.remove(targetId);
    }

    private void requireOwner(MemberId actorId) {
        Membership actor = membershipOf(actorId)
            .orElseThrow(() ->
                new DomainRuleViolation("Actor is not a team member")
            );

        if (actor.role() != TeamRole.OWNER) {
            throw new DomainRuleViolation(
                "Only an owner can manage team membership"
            );
        }
    }

    private int ownerCount() {
        return (int) memberships.values().stream()
            .filter(m -> m.role() == TeamRole.OWNER)
            .count();
    }

    private static String normalizeName(String value) {
        if (value == null || value.isBlank()) {
            throw new DomainRuleViolation(
                "Team name must not be blank"
            );
        }

        return value.trim();
    }

    public TeamId id() {
        return id;
    }

    public String name() {
        return name;
    }

    public boolean hasMember(MemberId memberId) {
        return memberships.containsKey(memberId);
    }

    public Optional<Membership> membershipOf(MemberId memberId) {
        return Optional.ofNullable(memberships.get(memberId));
    }

    public Collection<Membership> memberships() {
        return List.copyOf(memberships.values());
    }
}
~~~

Exception nghiệp vụ:

~~~java
public class DomainRuleViolation extends RuntimeException {

    public DomainRuleViolation(String message) {
        super(message);
    }
}
~~~

Aggregate này dùng Map trong bộ nhớ để tra cứu Membership theo member ID. Đây là cấu trúc của domain model; không có nghĩa database phải lưu graph theo cấu trúc map. SDN adapter có thể ánh xạ collection Membership thành relationship có properties theo thiết kế persistence.

## 5. Kiểm thử các quy tắc của aggregate

Unit test nên tập trung vào hành vi quan sát được. Không cần truy cập field private, tạo Spring context hoặc mock Neo4j.

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.time.Instant;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class TeamTest {

    private static final Instant CREATED_AT =
        Instant.parse("2026-01-10T09:00:00Z");

    private Team team;
    private MemberId ownerId;
    private MemberId memberId;

    @BeforeEach
    void setUp() {
        ownerId = new MemberId("owner-1");
        memberId = new MemberId("member-2");

        team = new Team(
            new TeamId("team-1"),
            "  Graph Platform  ",
            ownerId,
            CREATED_AT
        );
    }

    @Test
    void trimsNameAndCreatesFirstOwner() {
        assertThat(team.name()).isEqualTo("Graph Platform");
        assertThat(team.membershipOf(ownerId))
            .hasValueSatisfying(membership -> {
                assertThat(membership.role()).isEqualTo(TeamRole.OWNER);
                assertThat(membership.joinedAt()).isEqualTo(CREATED_AT);
            });
    }

    @Test
    void ownerCanAddMember() {
        Instant joinedAt = Instant.parse("2026-01-11T10:30:00Z");

        team.addMember(ownerId, memberId, joinedAt);

        assertThat(team.membershipOf(memberId))
            .hasValueSatisfying(membership -> {
                assertThat(membership.role()).isEqualTo(TeamRole.MEMBER);
                assertThat(membership.joinedAt()).isEqualTo(joinedAt);
            });
    }

    @Test
    void cannotAddTheSameMemberTwice() {
        team.addMember(ownerId, memberId, CREATED_AT);

        assertThatThrownBy(() ->
            team.addMember(ownerId, memberId, CREATED_AT)
        )
            .isInstanceOf(DomainRuleViolation.class)
            .hasMessage("Member already belongs to this team");

        assertThat(team.memberships()).hasSize(2);
    }

    @Test
    void nonOwnerCannotAddMember() {
        team.addMember(ownerId, memberId, CREATED_AT);

        assertThatThrownBy(() ->
            team.addMember(memberId, new MemberId("member-3"), CREATED_AT)
        )
            .isInstanceOf(DomainRuleViolation.class)
            .hasMessage("Only an owner can manage team membership");

        assertThat(team.memberships()).hasSize(2);
    }

    @Test
    void cannotRemoveTheLastOwner() {
        assertThatThrownBy(() ->
            team.removeMember(ownerId, ownerId)
        )
            .isInstanceOf(DomainRuleViolation.class)
            .hasMessage("The last owner cannot be removed");

        assertThat(team.membershipOf(ownerId)).isPresent();
    }

    @Test
    void cannotDemoteTheLastOwner() {
        assertThatThrownBy(() ->
            team.changeRole(ownerId, ownerId, TeamRole.MEMBER)
        )
            .isInstanceOf(DomainRuleViolation.class)
            .hasMessage("A team must have at least one owner");

        assertThat(team.membershipOf(ownerId))
            .get()
            .extracting(Membership::role)
            .isEqualTo(TeamRole.OWNER);
    }

    @Test
    void changingRoleKeepsOriginalJoinedAt() {
        team.addMember(ownerId, memberId, CREATED_AT);

        team.changeRole(ownerId, memberId, TeamRole.OWNER);

        assertThat(team.membershipOf(memberId))
            .hasValueSatisfying(membership -> {
                assertThat(membership.role()).isEqualTo(TeamRole.OWNER);
                assertThat(membership.joinedAt()).isEqualTo(CREATED_AT);
            });
    }

    @Test
    void ownerCanBeRemovedWhenAnotherOwnerRemains() {
        team.addMember(ownerId, memberId, CREATED_AT);
        team.changeRole(ownerId, memberId, TeamRole.OWNER);

        team.removeMember(ownerId, ownerId);

        assertThat(team.hasMember(ownerId)).isFalse();
        assertThat(team.membershipOf(memberId))
            .get()
            .extracting(Membership::role)
            .isEqualTo(TeamRole.OWNER);
    }
}
~~~

Các test trên kiểm tra cả kết quả thành công và trạng thái sau khi một quy tắc từ chối thao tác. Khi một hành động thất bại, aggregate phải giữ trạng thái hợp lệ.

### Kiểm thử dữ liệu đầu vào bằng parameterized test

Khi nhiều giá trị phải tuân cùng một quy tắc, dùng ParameterizedTest để tránh lặp test method:

~~~java
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.time.Instant;

import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

class TeamNameTest {

    @ParameterizedTest
    @ValueSource(strings = {"", " ", "   ", "\t"})
    void rejectsBlankName(String name) {
        assertThatThrownBy(() ->
            new Team(
                new TeamId("team-1"),
                name,
                new MemberId("owner-1"),
                Instant.parse("2026-01-10T09:00:00Z")
            )
        ).isInstanceOf(DomainRuleViolation.class);
    }
}
~~~

Có thể viết thêm test riêng cho null, vì ValueSource không cung cấp giá trị null.

## 6. Kiểm thử application service qua repository port

Domain model thường không tự đọc hoặc ghi database. Application service điều phối use case và phụ thuộc vào một abstraction để lưu aggregate.

Repository port:

~~~java
import java.util.Optional;

public interface TeamRepository {

    Optional<Team> findById(TeamId id);

    Team save(Team team);
}
~~~

Application service nhận Clock để thời gian có thể kiểm soát trong test:

~~~java
import java.time.Clock;

public class TeamApplicationService {

    private final TeamRepository teams;
    private final Clock clock;

    public TeamApplicationService(
            TeamRepository teams,
            Clock clock
    ) {
        this.teams = teams;
        this.clock = clock;
    }

    public void addMember(
            TeamId teamId,
            MemberId actorId,
            MemberId newMemberId
    ) {
        Team team = teams.findById(teamId)
            .orElseThrow(() ->
                new TeamNotFoundException(teamId)
            );

        team.addMember(actorId, newMemberId, clock.instant());
        teams.save(team);
    }
}
~~~

Exception cho trường hợp không tìm thấy nhóm:

~~~java
public class TeamNotFoundException extends RuntimeException {

    public TeamNotFoundException(TeamId teamId) {
        super("Team not found: " + teamId.value());
    }
}
~~~

Repository port có thể được triển khai bằng Spring Data Neo4j ở persistence adapter. Trong unit test của application service, chỉ cần một mock hoặc fake triển khai interface này.

## 7. Dùng mock để kiểm tra điều phối use case

Mock phù hợp khi muốn xác nhận application service gọi dependency đúng cách:

- Tìm aggregate theo ID.
- Không lưu nếu aggregate không tồn tại.
- Không lưu nếu quy tắc domain từ chối thao tác.
- Lưu aggregate sau khi thay đổi hợp lệ.

Ví dụ dùng JUnit 5, Mockito và AssertJ:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.mockito.ArgumentMatchers.any;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Optional;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class TeamApplicationServiceTest {

    private static final Instant NOW =
        Instant.parse("2026-02-01T12:00:00Z");

    @Mock
    private TeamRepository teams;

    private TeamApplicationService service;
    private Team team;
    private TeamId teamId;
    private MemberId ownerId;
    private MemberId newMemberId;

    @BeforeEach
    void setUp() {
        Clock fixedClock = Clock.fixed(NOW, ZoneOffset.UTC);
        service = new TeamApplicationService(teams, fixedClock);

        teamId = new TeamId("team-1");
        ownerId = new MemberId("owner-1");
        newMemberId = new MemberId("member-2");

        team = new Team(
            teamId,
            "Graph Platform",
            ownerId,
            Instant.parse("2026-01-01T00:00:00Z")
        );
    }

    @Test
    void addsMemberAndSavesUpdatedAggregate() {
        when(teams.findById(teamId)).thenReturn(Optional.of(team));

        service.addMember(teamId, ownerId, newMemberId);

        ArgumentCaptor<Team> captor =
            ArgumentCaptor.forClass(Team.class);

        verify(teams).save(captor.capture());

        assertThat(captor.getValue().membershipOf(newMemberId))
            .hasValueSatisfying(membership -> {
                assertThat(membership.role()).isEqualTo(TeamRole.MEMBER);
                assertThat(membership.joinedAt()).isEqualTo(NOW);
            });
    }

    @Test
    void doesNotSaveWhenTeamDoesNotExist() {
        when(teams.findById(teamId)).thenReturn(Optional.empty());

        assertThatThrownBy(() ->
            service.addMember(teamId, ownerId, newMemberId)
        ).isInstanceOf(TeamNotFoundException.class);

        verify(teams, never()).save(any());
    }

    @Test
    void doesNotSaveWhenDomainRuleRejectsActor() {
        when(teams.findById(teamId)).thenReturn(Optional.of(team));

        MemberId unknownActor = new MemberId("not-a-member");

        assertThatThrownBy(() ->
            service.addMember(teamId, unknownActor, newMemberId)
        ).isInstanceOf(DomainRuleViolation.class);

        verify(teams, never()).save(any());
        assertThat(team.hasMember(newMemberId)).isFalse();
    }
}
~~~

Mock xác nhận hợp đồng tương tác giữa application service và repository port. Nó không chứng minh repository SDN thực sự ghi đúng node hoặc relationship. Đó là trách nhiệm của test persistence/integration.

Nếu test chỉ cần xác nhận kết quả nghiệp vụ, không cần kiểm tra mọi lời gọi nội bộ. Hãy ưu tiên kiểm tra trạng thái cuối hoặc kết quả use case; chỉ verify tương tác khi việc gọi hoặc không gọi dependency là một phần quan trọng của hành vi.

## 8. Khi nào dùng fake repository?

Fake là một implementation đơn giản, chạy trong bộ nhớ và tuân theo contract của repository port. Nó hữu ích khi cần kiểm thử nhiều bước nghiệp vụ mà không muốn cấu hình nhiều stub.

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.Optional;

public final class InMemoryTeamRepository implements TeamRepository {

    private final Map<TeamId, Team> store = new HashMap<>();

    public void addFixture(Team team) {
        store.put(team.id(), team);
    }

    @Override
    public Optional<Team> findById(TeamId id) {
        return Optional.ofNullable(store.get(id));
    }

    @Override
    public Team save(Team team) {
        store.put(team.id(), team);
        return team;
    }
}
~~~

Ví dụ test use case với fake:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

@Test
void addsMemberToExistingTeamUsingInMemoryRepository() {
    TeamId teamId = new TeamId("team-1");
    MemberId ownerId = new MemberId("owner-1");
    MemberId memberId = new MemberId("member-2");

    Team team = new Team(
        teamId,
        "Graph Platform",
        ownerId,
        Instant.parse("2026-01-01T00:00:00Z")
    );

    InMemoryTeamRepository repository =
        new InMemoryTeamRepository();
    repository.addFixture(team);

    TeamApplicationService service =
        new TeamApplicationService(
            repository,
            Clock.fixed(
                Instant.parse("2026-02-01T12:00:00Z"),
                ZoneOffset.UTC
            )
        );

    service.addMember(teamId, ownerId, memberId);

    assertThat(repository.findById(teamId))
        .get()
        .satisfies(saved ->
            assertThat(saved.hasMember(memberId)).isTrue()
        );
}
~~~

Fake này chỉ mô phỏng thao tác lưu và tìm aggregate trong bộ nhớ. Không nên bổ sung Cypher parser, transaction engine hoặc cơ chế giả lập SDN vào fake. Một bản mô phỏng như vậy dễ khác hành vi database thật và tạo cảm giác an toàn sai lệch.

## 9. Kiểm thử relationship như một phần của mô hình graph

Relationship có thể mang thuộc tính nghiệp vụ, do đó cần test cả hai đầu liên kết và dữ liệu trên quan hệ.

Ví dụ với Membership:

- Có đúng memberId cần liên kết.
- Vai trò đúng sau khi thêm hoặc thay đổi.
- joinedAt không bị thay đổi khi chỉ đổi vai trò.
- Không tạo hai quan hệ Membership cho cùng một member trong cùng Team.
- Không xóa quan hệ nếu thao tác vi phạm invariant của aggregate.

Hãy xác định rõ collection có yêu cầu thứ tự hay không. Nếu thứ tự không phải quy tắc nghiệp vụ, đừng viết test phụ thuộc vào thứ tự duyệt Map, Set hoặc kết quả query.

Nếu relationship có direction, type hoặc cardinality cần được SDN ánh xạ chính xác, unit test domain chỉ xác nhận ý nghĩa nghiệp vụ. Ví dụ, test Membership không thể chứng minh SDN đã lưu relationship theo hướng Team-[:HAS_MEMBER]->Member. Cần integration test cho mapping đó.

## 10. Kiểm soát thời gian, UUID và dependency không xác định

Test thường không ổn định khi business code trực tiếp gọi:

- Instant.now().
- LocalDateTime.now().
- UUID.randomUUID().
- Random number generator.
- Dịch vụ bên ngoài hoặc biến môi trường.

Hãy đưa các nguồn biến động thành dependency có thể thay thế.

Với thời gian, dùng Clock:

~~~java
Clock fixedClock = Clock.fixed(
    Instant.parse("2026-02-01T12:00:00Z"),
    ZoneOffset.UTC
);
~~~

Với định danh, có thể định nghĩa port:

~~~java
public interface IdGenerator {
    String nextId();
}
~~~

Trong test, cung cấp implementation trả một ID cố định. Nhờ vậy, test không cần đoán giá trị ngẫu nhiên và có thể kiểm tra chính xác kết quả.

Đừng dùng Thread.sleep() để chờ thời gian thay đổi trong test. Hãy điều khiển clock và truyền giá trị thời gian xác định.

## 11. Những gì unit test không thể chứng minh

Không có Neo4j nghĩa là test không chạy Neo4j query engine hoặc SDN mapping infrastructure. Vì vậy, không thể dùng unit test để kết luận các hành vi sau hoạt động đúng:

| Điều cần xác minh | Vì sao unit test chưa đủ |
|---|---|
| @Node ánh xạ đúng label | Cần kiểm tra mapping của SDN |
| @Relationship có đúng type và direction | Cần đọc graph sau khi ghi |
| @RelationshipProperties lưu đúng property | Cần kiểm tra record thực tế trong Neo4j |
| Repository query trả kết quả đúng | Cần thực thi Cypher |
| MERGE có xử lý đúng dữ liệu trùng | Cần chạy query trên database |
| Transaction rollback đúng | Cần quan sát trạng thái sau transaction |
| Index/constraint được tạo và áp dụng | Cần kiểm tra schema database |
| Locking hoặc optimistic version hoạt động | Cần test với các transaction cạnh tranh |

Không nên thêm @DataNeo4jTest vào unit test chỉ để có thể inject repository. Test slice này nhằm kiểm thử phần tích hợp SDN và cần cấu hình kết nối Neo4j phù hợp. Tài liệu SDN cũng nêu rõ @DataNeo4jTest cung cấp transaction manager, client, template và repository infrastructure nhưng không tự cung cấp database hoặc connection setting. Có thể dùng Testcontainers hoặc Neo4j Test Harness cho loại test đó.

## 12. Cấu trúc thư mục test gợi ý

Tổ chức test theo lớp nghiệp vụ giúp người đọc hiểu test đang bảo vệ điều gì:

~~~text
src
├── main
│   └── java
│       └── ...
│           ├── domain
│           │   ├── Team.java
│           │   ├── Membership.java
│           │   └── TeamRole.java
│           ├── application
│           │   └── TeamApplicationService.java
│           └── persistence
│               └── neo4j
│                   └── TeamRepositoryAdapter.java
└── test
    └── java
        └── ...
            ├── domain
            │   └── TeamTest.java
            ├── application
            │   └── TeamApplicationServiceTest.java
            └── persistence
                └── neo4j
                    └── TeamRepositoryIntegrationTest.java
~~~

domain và application test chạy nhanh, không cần Neo4j. persistence/neo4j dành cho các test cần kiểm tra adapter, mapping hoặc query thật.

Tên thư mục chỉ là gợi ý; hãy giữ cách tổ chức phù hợp với cấu trúc module hiện tại.

## 13. Dependency kiểm thử

Nếu dùng Spring Boot, dependency test phổ biến là:

~~~gradle
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
~~~

Starter này cung cấp các công cụ kiểm thử thường dùng như JUnit Jupiter, Mockito và AssertJ theo dependency management của Spring Boot.

Nếu không dùng Spring Boot, có thể khai báo riêng JUnit Jupiter, Mockito và AssertJ:

~~~gradle
dependencies {
    testImplementation("org.junit.jupiter:junit-jupiter")
    testImplementation("org.mockito:mockito-junit-jupiter")
    testImplementation("org.assertj:assertj-core")
}
~~~

JUnit parameterized test cần module junit-jupiter-params; khi dùng Spring Boot starter test hoặc dependency aggregate phù hợp, hãy kiểm tra dependency tree để bảo đảm module này có mặt.

Không cần thêm Neo4j Driver, Testcontainers hoặc SDN test slice chỉ để chạy các unit test thuần Java ở bài này.

## 14. Checklist thiết kế unit test nghiệp vụ

Trước khi hoàn tất một nhóm test, hãy tự kiểm tra:

- Mỗi test thể hiện một quy tắc hoặc một hành vi có ý nghĩa.
- Có test cho đường thành công và đường bị từ chối.
- Sau lỗi, trạng thái aggregate vẫn hợp lệ.
- Relationship properties được kiểm tra cùng với liên kết.
- Test không phụ thuộc thứ tự collection nếu nghiệp vụ không yêu cầu.
- Thời gian và định danh được kiểm soát.
- Mock chỉ kiểm tra tương tác cần thiết.
- Fake không cố mô phỏng Neo4j hoặc Cypher.
- Không khởi động Spring context khi test chỉ cần Java object.
- Các hành vi mapping, query và transaction được dành cho integration test.

## 15. Bài tập thực hành

Mở rộng mô hình Team với quy tắc: một Team có thể có nhiều Member, nhưng chỉ Owner được đổi vai trò; Team không thể mất Owner cuối cùng.

Thực hiện:

1. Viết value object TeamId và MemberId.
2. Viết Membership có memberId, role và joinedAt.
3. Tạo aggregate Team với ít nhất một owner.
4. Viết test tạo Team với tên hợp lệ và từ chối tên rỗng.
5. Viết test thêm thành viên và từ chối member trùng lặp.
6. Viết test thành viên thường không thể quản lý membership.
7. Viết test không thể xóa hoặc hạ vai trò owner cuối cùng.
8. Viết test đổi vai trò nhưng giữ nguyên joinedAt.
9. Viết TeamRepository port và TeamApplicationService.
10. Dùng Clock.fixed để test thời điểm thêm thành viên.
11. Viết test service bằng Mockito hoặc InMemoryTeamRepository.
12. Liệt kê các quy tắc cần integration test khi Team và Membership được ánh xạ sang Neo4j.

Câu hỏi tự kiểm tra:

- Vì sao có thể test quy tắc domain mà không cần Neo4j?
- Một relationship có thuộc tính nên được kiểm thử như thế nào?
- Khi nào nên dùng mock và khi nào nên dùng fake?
- Vì sao fake repository không nên mô phỏng Cypher?
- Clock.fixed giúp test ổn định ra sao?
- Unit test có chứng minh được relationship direction không?
- Khi nào cần DataNeo4jTest hoặc Testcontainers?
- Vì sao test trạng thái sau một thao tác thất bại quan trọng?
- Vì sao không nên kiểm tra private field trực tiếp?

## Kết luận

Mô hình nghiệp vụ của ứng dụng Spring Data Neo4j vẫn là các object Java có thể kiểm thử độc lập. Value object, aggregate và relationship có thuộc tính có thể được kiểm tra bằng JUnit mà không cần khởi động Neo4j. Application service cũng có thể được kiểm thử bằng repository port với mock hoặc fake, đồng thời dùng Clock và ID generator để loại bỏ nguồn biến động.

Hãy dùng unit test để bảo vệ quy tắc nghiệp vụ và integration test để xác minh SDN mapping, Cypher, repository cùng transaction. Giữ hai phạm vi rõ ràng giúp test chạy nhanh, dễ hiểu và cho biết chính xác lỗi nằm ở mô hình nghiệp vụ hay ở tầng persistence.

## Tài liệu tham khảo

- [Spring Data Neo4j: Testing with Spring Boot and DataNeo4jTest](https://docs.spring.io/spring-data/neo4j/reference/testing/testing-with-spring-boot.html)
- [Spring Boot: Testing Spring Boot applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
- [JUnit 5 User Guide: Writing tests and parameterized tests](https://docs.junit.org/current/user-guide/)
- [Mockito: Documentation](https://site.mockito.org/)
- [AssertJ: Core assertions](https://assertj.github.io/doc/)
