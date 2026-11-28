# Inherited permission

## 1. Quyền kế thừa là gì?

**Inherited permission**, hay quyền kế thừa, là quyền trên một tài nguyên được suy ra từ quan hệ với tài nguyên khác theo policy của hệ thống. Chủ thể không nhất thiết được gán quyền trực tiếp lên từng đối tượng mà họ có thể truy cập.

Ví dụ, Lan được phép đọc thư mục “Nhân sự”. Nếu policy quy định tài liệu con kế thừa quyền đọc của thư mục cha, Lan có thể đọc một tài liệu trong thư mục đó dù tài liệu không có grant trực tiếp cho Lan.

Trong ReBAC, quyết định có thể được giải thích bằng một đường quan hệ:

```text
Lan có quyền đọc thư mục A
Tài liệu D có parent là thư mục A
Policy cho quyền đọc của A truyền xuống D
=> Lan được đọc D
```

Điểm quyết định là **policy cho phép truyền quyền nào qua quan hệ nào**. Việc hai tài nguyên có liên hệ, cùng đường dẫn hoặc cùng owner không tự làm cho mọi quyền được kế thừa.

Quyền kế thừa giúp quản lý truy cập theo tổ chức tài nguyên, nhưng cũng làm phạm vi tác động của thay đổi quyền rộng hơn. Một thay đổi trên thư mục có thể ảnh hưởng hàng nghìn tài liệu bên dưới; một thao tác di chuyển tài liệu có thể thay đổi người được đọc mà không sửa bất kỳ grant trực tiếp nào trên tài liệu.

Sau bài học, người học có thể:

- Phân biệt quyền trực tiếp, quyền kế thừa và quyền hiệu lực.
- Viết quy tắc truyền quyền đọc, sửa và quản lý mà không làm lẫn ownership.
- Nhận diện các đường truy cập còn tồn tại sau khi gỡ một grant.
- Bảo vệ thao tác thay đổi quan hệ cha–con và giới hạn phạm vi tenant.
- Xử lý vòng lặp, lỗi dữ liệu, cache và độ trễ thu hồi khi đánh giá quyền.

## 2. Ba khái niệm cần tách rõ

### 2.1. Direct permission: quyền được cấp tại đối tượng đang xét

Một grant trực tiếp có thể được biểu diễn bằng bộ ba:

```text
(user:mai, viewer, document:budget-2026)
```

Mai được gán quan hệ viewer trực tiếp với tài liệu. Nếu tài liệu đổi thư mục nhưng grant này vẫn tồn tại, Mai có thể tiếp tục đọc theo policy viewer của ứng dụng.

### 2.2. Inherited permission: quyền đến qua một đường quan hệ

Một đường kế thừa đơn giản gồm hai quan hệ:

```text
(user:lan, viewer, folder:hr)
(folder:hr, parent, document:budget-2026)
```

Ở đây, bộ ba thứ hai dùng cách viết `(subject, relation, object)`: `folder:hr` là parent của `document:budget-2026`. Có thể diễn đạt tương đương là `parent(document:budget-2026) = folder:hr`.

Nếu model cho phép kế thừa viewer từ parent, quyền đọc của Lan trên tài liệu được suy ra từ đường này. Không cần tạo một cạnh viewer trực tiếp cho Lan trên mọi tài liệu con.

Tài liệu [OpenFGA về parent–child objects](https://openfga.dev/docs/modeling/parent-child) minh họa cách một quan hệ của người dùng với thư mục ảnh hưởng đến quyền trên tài liệu thông qua model được cấu hình. Quan hệ parent và quy tắc suy ra đều cần được định nghĩa; không chỉ tạo liên kết chứa tài liệu là đủ.

### 2.3. Effective permission: quyền cuối cùng sau khi áp dụng policy

Quyền hiệu lực là kết quả xét các nguồn quyền cùng những điều kiện bắt buộc. Một mô hình đơn giản có thể dùng:

```text
được đọc tài liệu =
    điều kiện danh tính và tenant hợp lệ
    AND trạng thái tài nguyên cho phép
    AND (quyền đọc trực tiếp OR quyền đọc kế thừa)
```

Nếu có quy tắc chặn, ngoại lệ hoặc yêu cầu xác thực bổ sung, chúng cũng phải tham gia quyết định theo cách kết hợp đã được định nghĩa.

| Khái niệm | Nơi xuất phát | Khi đổi parent có thể thay đổi không? |
| --- | --- | --- |
| Quyền trực tiếp | Grant trên chính tài nguyên | Không nhất thiết, nếu grant được giữ nguyên |
| Quyền kế thừa | Quan hệ với tài nguyên khác và quy tắc truyền quyền | Có |
| Quyền hiệu lực | Toàn bộ policy, quan hệ và điều kiện đang áp dụng | Có, kể cả khi grant trực tiếp không đổi |

Không tìm thấy grant trực tiếp chưa đủ để kết luận người dùng không có quyền. Ngược lại, tìm thấy một đường cấp quyền cũng chưa đủ nếu điều kiện bắt buộc của toàn policy không đạt.

## 3. Một mô hình kế thừa cha–con cụ thể

### 3.1. Cấu trúc tài nguyên minh họa

Xét ứng dụng lưu tài liệu cho nhiều doanh nghiệp. Trong tenant A có cây sau:

```text
folder:hr
└── folder:planning
    ├── document:budget-2026
    └── document:hiring-plan
```

Ứng dụng sử dụng các quan hệ trực tiếp sau:

```text
Lan là viewer của folder:hr
Nam là editor của folder:planning
Mai là viewer trực tiếp của document:budget-2026
Huy là owner trực tiếp của document:budget-2026
```

Mỗi đối tượng có tối đa một parent; parent phải là folder cùng tenant. Cây không có chu trình. Đây là lựa chọn của ví dụ, không phải ràng buộc chung cho mọi hệ thống ReBAC.

### 3.2. Chọn permission nào được truyền

Policy của ví dụ quy định:

```text
local_read(user, object)
    = owner(user, object)
      OR editor(user, object)
      OR viewer(user, object)

local_edit(user, object)
    = owner(user, object)
      OR editor(user, object)

can_read(user, object)
    = local_read(user, object)
      OR can_read(user, parent(object))

can_edit(user, object)
    = local_edit(user, object)
      OR can_edit(user, parent(object))

can_manage_sharing(user, object)
    = owner(user, object)

can_transfer_ownership(user, object)
    = owner(user, object)
```

Nếu không có parent, nhánh kế thừa không tạo quyền. Đây là ký pháp giải thích policy; nó không phải đoạn cấu hình dùng nguyên văn cho mọi engine.

Các công thức trên mô tả nguồn cấp quyền. Điều kiện tài khoản, phiên, membership, tenant và trạng thái tài nguyên vẫn phải được kiểm tra ở policy đầy đủ.

Với lựa chọn này, quyền đọc và sửa được truyền xuống. Quyền quản lý chia sẻ và chuyển ownership chỉ đến từ owner trực tiếp của đối tượng đang xét. Owner của thư mục cha có thể đọc hoặc sửa tài liệu con theo quy tắc truyền permission, nhưng không trở thành owner trực tiếp của tài liệu con.

### 3.3. Kết quả với từng người dùng

| Chủ thể | Đọc budget-2026 | Sửa budget-2026 | Chuyển ownership của budget-2026 |
| --- | --- | --- | --- |
| Lan | Có, qua quyền đọc của hr | Không từ các quan hệ đã nêu | Không |
| Nam | Có, qua quyền editor của planning | Có, qua planning | Không |
| Mai | Có, từ viewer trực tiếp | Không từ các quan hệ đã nêu | Không |
| Huy | Có, từ owner trực tiếp | Có, từ owner trực tiếp | Có nếu các điều kiện khác đạt |

Quyền từ cha xuống con không tự chạy theo chiều ngược lại. Mai được đọc budget-2026 không có nghĩa Mai được liệt kê mọi tài liệu trong planning. Nam được sửa tài liệu trong planning cũng không vì thế được sửa folder:hr.

Để giao diện hiển thị đường dẫn, sản phẩm có thể có permission riêng cho tên thư mục hoặc điều hướng. Không nên vô tình cấp quyền đọc toàn bộ cây chỉ để hiển thị breadcrumb của một tài liệu được chia sẻ trực tiếp.

## 4. Kế thừa quyền khác với sao chép quyền

### 4.1. Suy ra tại thời điểm kiểm tra

Nếu hệ thống đánh giá từ đồ thị quan hệ, chỉ cần lưu grant ở cấp cha và liên kết parent. Khi thêm tài liệu con mới, nó có thể nhận quyền kế thừa ngay theo model, không cần ghi lại grant cho từng người dùng.

Khi gỡ viewer của Lan tại hr, đường kế thừa qua hr không còn hợp lệ đối với các lần đánh giá dùng dữ liệu cập nhật. Tuy nhiên, Lan có thể vẫn có đường truy cập khác hoặc kết quả cũ trong cache; việc thu hồi thực tế cần xét cả hai.

### 4.2. Sao chép grant xuống tài nguyên con

Một ứng dụng khác có thể sao chép ACL của cha vào con khi tạo tài nguyên. Nếu các bản sao trở thành grant độc lập, gỡ grant ở cha không nhất thiết xóa chúng. Đây là hành vi khác với kế thừa động.

Nếu dùng bảng quyền đã tính sẵn để tăng tốc, cần giữ được nguồn gốc và quy tắc cập nhật. Bảng đó có thể là bản sao dẫn xuất của policy, nhưng chỉ đúng khi các thay đổi ở grant, membership, parent và model được phản ánh phù hợp.

| Cách triển khai | Khi gỡ quyền tại cha | Trách nhiệm chính |
| --- | --- | --- |
| Suy ra từ quan hệ khi kiểm tra | Đường kế thừa không còn nếu dữ liệu đọc đã cập nhật | Nhất quán dữ liệu, truy vấn và cache |
| Sao chép thành grant trực tiếp độc lập | Grant ở con có thể còn | Định nghĩa rõ hành vi sao chép và thu hồi |
| Tính sẵn quyền hiệu lực | Phụ thuộc việc cập nhật dữ liệu dẫn xuất | Theo dõi phụ thuộc, phiên bản và độ trễ |

Không nên dùng tên “inherit” cho một cơ chế sao chép một lần mà không giải thích khác biệt. Người quản trị có thể tưởng đã thu hồi ở cấp cha trong khi quyền tại con vẫn còn.

## 5. Nhiều đường cấp quyền, quy tắc chặn và điểm dừng kế thừa

### 5.1. Gỡ một đường không phải gỡ mọi đường

Nếu Lan vừa là viewer của hr, vừa là viewer trực tiếp của budget-2026, việc gỡ viewer ở hr chỉ xóa một nguồn quyền. Lan vẫn có thể đọc budget-2026 qua grant trực tiếp.

Tương tự, quyền có thể đi qua nhóm:

```text
Lan là member của team:finance
team:finance được đọc folder:planning
budget-2026 nằm trong planning
```

Đường này kết hợp hai kiểu suy ra: membership của nhóm và kế thừa tài nguyên. Cần xem xét cả grant trên tài nguyên lẫn thành viên nhóm khi giải thích hoặc thu hồi quyền.

### 5.2. Không có allow trực tiếp không đồng nghĩa có deny

Một danh sách viewer trực tiếp rỗng chỉ cho biết không có viewer được gán trực tiếp. Nó không tự chặn quyền đọc từ parent.

Nếu cần một tài liệu riêng tư nằm dưới thư mục chia sẻ rộng, sản phẩm phải có cơ chế rõ ràng, chẳng hạn:

- Đặt tài liệu trong một nhánh có phạm vi chia sẻ phù hợp.
- Có cấu hình dừng kế thừa được policy hỗ trợ.
- Có quy tắc chặn người dùng hoặc nhóm theo cách kết hợp đã định nghĩa.

Không tự giả định rằng một grant ở con luôn ghi đè mọi grant ở cha. Mô hình dùng phép hợp các nguồn allow thường không có hành vi “cấp gần hơn thắng” nếu không được bổ sung quy tắc đó.

### 5.3. Điểm dừng phải gắn với permission cụ thể

Một biến thể của policy có thể viết:

```text
can_read(user, object) =
    local_read(user, object)
    OR (object.inheritRead AND can_read(user, parent(object)))
```

Khi `inheritRead = false`, nhánh đọc từ parent bị ngắt ở đối tượng đó. Các grant đọc trực tiếp vẫn có thể hoạt động. Việc ngắt quyền đọc không tự ngắt quyền sửa hoặc quản lý nếu các permission ấy dùng công thức khác.

Thay đổi cấu hình kế thừa là thay đổi policy có tác động đến truy cập. Trong mô hình dừng ở giữa cây, các đối tượng con sâu hơn cũng có thể bị ảnh hưởng. Không nên cho mọi editor được sửa cờ này chỉ vì họ có quyền sửa nội dung.

### 5.4. Allow và deny cần quy tắc kết hợp

Nếu có deny, phải xác định nó áp dụng tại đối tượng nào, truyền theo chiều nào và có ưu tiên ra sao. Ví dụ, một deny ở folder có chặn cả grant trực tiếp của tài liệu con hay không là quyết định thiết kế.

Không nên chèn một điều kiện `if denied then false` tùy ý vào một phần đường duyệt mà không xét các nhánh khác. Với nhiều policy hoặc nhiều parent, việc kết hợp kết quả cần nhất quán trên toàn mô hình.

Ví dụ triển khai chính trong bài dùng một cây, các grant allow và điều kiện bắt buộc; chưa triển khai deny hay cấu hình dừng kế thừa. Những tính năng đó cần được mô hình và kiểm thử riêng khi bổ sung.

## 6. Ranh giới tenant và tính hợp lệ của cấu trúc

### 6.1. Parent là dữ liệu bảo mật

Một editor có thể thử thay `parentId` của tài liệu để đưa nó vào một thư mục mà mình quản lý. Nếu backend coi parent chỉ là metadata mô tả, thao tác này có thể tạo một đường cấp quyền mới ngoài ý định.

Quan hệ parent cần được quản lý bằng luồng được ủy quyền. Không cho phép API sửa tiêu đề tự động cập nhật thêm parent từ JSON vì DTO được ánh xạ quá rộng.

Việc đổi parent còn có thể mở tài liệu cho một nhóm người mới. Vì vậy, quyền sửa nội dung không nhất thiết bao gồm quyền di chuyển tài nguyên hoặc thay đổi phạm vi chia sẻ.

### 6.2. Không truyền quyền xuyên tenant ngoài policy

Trong ví dụ, mọi cạnh parent phải nối hai đối tượng cùng tenant. Khi đọc một tài liệu thuộc tenant A, hệ thống không được đi theo một parent thuộc tenant B rồi dùng quyền của B để cho phép trên A.

Ràng buộc này cần được kiểm tra ở lúc ghi quan hệ và được bảo vệ ở đường đánh giá. Nếu dữ liệu cấu trúc bị lỗi, backend không nên chọn một nhánh cho quyền rộng hơn để tiếp tục.

Chia sẻ liên tenant nếu được hỗ trợ là một nghiệp vụ riêng. Nó cần quan hệ, chủ thể nhận, điều kiện tổ chức và permission cụ thể; không dùng một cạnh parent bất hợp lệ để tạo hành vi chia sẻ ngầm.

### 6.3. Cây, đồ thị nhiều parent và chu trình

Một cây có tối đa một parent cho mỗi đối tượng. Một đồ thị có thể cho phép nhiều parent, khi đó phải chọn cách kết hợp: quyền từ bất kỳ parent nào, từ tất cả parent hay từ các loại quan hệ khác nhau.

Trong model dùng phép hợp, chỉ cần một đường hợp lệ có thể tạo quyền. Nhưng điều kiện bắt buộc như tenant, trạng thái tài khoản hoặc một quy tắc chặn toàn cục vẫn phải được giữ. Nhiều parent không có nghĩa điều kiện an toàn của toàn policy trở thành tùy chọn.

Chu trình như `A -> B -> C -> A` có thể khiến cách duyệt ngây thơ lặp vô hạn. Hệ thống nên kiểm tra khi ghi, theo dõi nút trên đường duyệt và có giới hạn tài nguyên đánh giá. Nếu dùng giới hạn độ sâu, chạm giới hạn không phải bằng chứng người dùng được phép.

Với đồ thị nhiều nhánh, một tập visited dùng sai có thể làm bỏ qua đường hợp lệ. Cần phân biệt phát hiện chu trình trên đường đang xét với ghi nhớ kết quả đã tính; nếu có memoization thì khóa phải phản ánh subject, permission, đối tượng và snapshot/policy liên quan.

## 7. Ví dụ Java: tính quyền đọc và sửa trên một cây

### 7.1. Phạm vi của ví dụ

Đoạn mã sau thực hiện model một parent và phép hợp các nguồn allow ở mục 3. Ngoài kiểm tra danh tính và membership, ví dụ chọn quy tắc bổ sung: tài nguyên đích và mọi ancestor trên đường đến gốc phải còn hoạt động, cùng tenant và có cấu trúc hợp lệ.

Ứng dụng cung cấp một snapshot quan hệ nhất quán từ nguồn có thẩm quyền. Snapshot phải chứa chuỗi ancestor cần kiểm tra, kể cả khi người dùng không được cấp riêng permission liệt kê các thư mục đó. Backend được đọc cấu trúc để đánh giá quyền không có nghĩa được trả toàn bộ cấu trúc ấy cho người gọi.

`Context` là dữ liệu nội bộ từ lớp xác thực và kiểm tra membership; không nhận các trường Boolean từ request body. Ví dụ không hỗ trợ nhóm lồng nhau, nhiều parent, deny hoặc điểm dừng kế thừa.

```java
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

public final class InheritedPermissionPolicy {
    private static final int MAX_PATH_NODES = 64;

    public enum Kind { FOLDER, DOCUMENT }
    public enum Permission { READ, EDIT }
    public enum Decision { ALLOW, DENY, INDETERMINATE }

    public record Context(
            String subjectId,
            String tenantId,
            boolean authenticated,
            boolean accountActive,
            boolean sessionActive,
            boolean membershipActive) {
    }

    public record Node(
            String id,
            Kind kind,
            String tenantId,
            String parentId,
            String ownerId,
            boolean active,
            Set<String> editors,
            Set<String> viewers) {
        public Node {
            editors = Set.copyOf(editors);
            viewers = Set.copyOf(viewers);
        }
    }

    public record Snapshot(Map<String, Node> nodes) {
        public Snapshot {
            nodes = Map.copyOf(nodes);
        }
    }

    public static Decision check(
            Context context, Snapshot snapshot,
            String targetId, Permission permission) {
        if (context == null || snapshot == null || permission == null
                || blank(targetId) || blank(context.subjectId())
                || blank(context.tenantId())) {
            return Decision.INDETERMINATE;
        }

        if (!context.authenticated() || !context.accountActive()
                || !context.sessionActive() || !context.membershipActive()) {
            return Decision.DENY;
        }

        Set<String> path = new HashSet<>();
        String currentId = targetId;
        boolean granted = false;

        for (int depth = 0; depth < MAX_PATH_NODES; depth++) {
            if (!path.add(currentId)) {
                return Decision.INDETERMINATE;
            }

            Node node = snapshot.nodes().get(currentId);
            if (node == null || !currentId.equals(node.id())
                    || node.kind() == null || blank(node.tenantId())
                    || blank(node.ownerId())) {
                return Decision.INDETERMINATE;
            }

            if (!context.tenantId().equals(node.tenantId()) || !node.active()) {
                return Decision.DENY;
            }

            if (depth > 0 && node.kind() != Kind.FOLDER) {
                return Decision.INDETERMINATE;
            }

            boolean localEdit = context.subjectId().equals(node.ownerId())
                    || node.editors().contains(context.subjectId());
            boolean localRead = localEdit
                    || node.viewers().contains(context.subjectId());

            granted |= permission == Permission.READ ? localRead : localEdit;

            if (node.parentId() == null) {
                return granted ? Decision.ALLOW : Decision.DENY;
            }
            if (blank(node.parentId())) {
                return Decision.INDETERMINATE;
            }
            currentId = node.parentId();
        }

        return Decision.INDETERMINATE;
    }

    private static boolean blank(String value) {
        return value == null || value.isBlank();
    }
}
```

### 7.2. Vì sao chưa trả allow ngay khi gặp một grant?

Biến `granted` ghi nhận đã tìm thấy nguồn cấp quyền, nhưng hàm tiếp tục kiểm tra chuỗi ancestor. Đây là lựa chọn thận trọng của ví dụ vì model yêu cầu toàn bộ chuỗi có cấu trúc hợp lệ, cùng tenant và đang hoạt động.

Nếu parent bị thiếu, có chu trình hoặc vượt giới hạn, hàm trả `INDETERMINATE`, ngay cả khi đã gặp grant trực tiếp. Với quy tắc này, dữ liệu cấu trúc lỗi không được dùng để cấp quyền. Đây không phải quy tắc đánh giá duy nhất của mọi engine: một model khác có thể cho phép khi đã chứng minh được một nhánh allow độc lập và mọi điều kiện bắt buộc liên quan đều đạt.

Điểm thực thi chỉ thực hiện thao tác khi nhận `ALLOW`. `DENY` biểu thị các điều kiện đã xét không cho phép; `INDETERMINATE` biểu thị không đánh giá được hợp lệ. Không được biến lỗi đọc parent hoặc lỗi dựng snapshot thành một danh sách quyền trống rồi tự cho phép.

Giới hạn 64 là số nút tối đa trên đường kiểm tra, tính cả đối tượng đích. Nó chỉ phục vụ ví dụ. Một đường gồm 64 nút có gốc ở nút cuối vẫn có thể được đánh giá; nếu cần đi tiếp đến nút thứ 65 thì kết quả không xác định. Giới hạn phải phù hợp với cấu trúc hợp lệ mà sản phẩm cam kết hỗ trợ.

`Set.copyOf` và `Map.copyOf` giúp tránh sửa các collection của snapshot sau khi tạo. Chúng không tự chứng minh rằng dữ liệu đã được đọc từ một phiên bản nhất quán của database. Hệ thống vẫn cần cơ chế snapshot, phiên bản hoặc giao dịch phù hợp ở lớp cung cấp dữ liệu.

Nếu dữ liệu collection không hợp lệ khiến việc dựng record thất bại, lớp gọi phải chặn thao tác cần quyết định quyền và xử lý lỗi; không bắt exception rồi mặc định trả allow.

### 7.3. Độ phức tạp và phạm vi mở rộng

Với cây một parent và phép tra cứu map trung bình hằng số, việc kiểm tra cần đi qua tối đa số nút trên chuỗi ancestor. Tập `path` cũng tăng theo chiều dài chuỗi. Đây là cách minh họa dễ quan sát, không phải một engine quyền tổng quát.

Khi chuyển sang nhiều parent hoặc nhóm lồng nhau, số nhánh có thể tăng. Cần giới hạn tổng công việc, phát hiện chu trình đúng và tận dụng kết quả đã tính trong cùng snapshot. Không mở rộng mã bằng cách đệ quy không giới hạn hoặc mặc định lỗi ở một nhánh luôn có thể bỏ qua.

## 8. Thay parent hoặc di chuyển tài nguyên là thay đổi quyền

### 8.1. Tập người được truy cập có thể đổi mà grant trực tiếp giữ nguyên

Giả sử budget-2026 được chuyển từ planning sang một thư mục chung company-wide. Policy đọc của thư mục đích có thể làm tài liệu xuất hiện với toàn bộ nhân viên, dù danh sách viewer trực tiếp của tài liệu không thay đổi.

Theo chiều ngược lại, chuyển tài liệu sang một nhánh hạn chế hơn có thể thu hồi các đường kế thừa từ vị trí cũ. Tuy nhiên, grant trực tiếp hoặc nhóm khác vẫn có thể giữ quyền.

Vì thế, một API di chuyển cần kiểm tra riêng quyền tại nguồn, quyền đặt tài nguyên vào đích và quyền thay đổi phạm vi truy cập theo policy của sản phẩm. Một người chỉ được xem thư mục đích không nhất thiết được phép đưa tài liệu nhạy cảm vào đó.

### 8.2. Những điều kiện cần kiểm tra khi di chuyển

Một luồng của ứng dụng ví dụ có thể gồm:

1. Xác thực người gọi, tenant và permission di chuyển đối tượng nguồn.
2. Kiểm tra thư mục đích tồn tại, đúng loại, cùng tenant và cho phép nhận tài nguyên.
3. Xác minh việc di chuyển không tạo chu trình hoặc vượt cấu trúc được hỗ trợ.
4. Đánh giá thay đổi phạm vi quyền theo các quy tắc chia sẻ của sản phẩm.
5. Cập nhật parent với điều kiện về phiên bản và các ràng buộc cần thiết.
6. Ghi audit, cập nhật dữ liệu dẫn xuất và xử lý cache liên quan.

Nếu di chuyển cả thư mục, những tài nguyên con sâu hơn cũng bị ảnh hưởng bởi đường kế thừa mới. Không chỉ so sánh permission của chính folder được di chuyển.

### 8.3. Cập nhật đồng thời và giới hạn của kiểm tra phiên bản

Backend có thể ràng buộc thay đổi parent của đối tượng với phiên bản đã kiểm tra:

```sql
UPDATE resource
SET parent_id = :authorized_destination_id,
    structure_version = structure_version + 1
WHERE tenant_id = :authorized_tenant_id
  AND id = :resource_id
  AND structure_version = :expected_structure_version;
```

Nếu không cập nhật được đúng một dòng, không coi thao tác di chuyển đã thành công. Đoạn SQL chỉ bảo vệ xung đột trên đối tượng được cập nhật; nó chưa thay thế kiểm tra quyền nguồn, đích và tính hợp lệ của cả cấu trúc.

Ví dụ, hai giao dịch đồng thời đặt A dưới B và B dưới A có thể cùng thấy cấu trúc ban đầu không có chu trình. So sánh phiên bản riêng của A và B vẫn có thể không ngăn được kết quả có chu trình nếu cả hai thao tác đều commit.

Để giữ bất biến toàn cây, cần cơ chế giao dịch, khóa hoặc tuần tự hóa thích hợp với các thay đổi cấu trúc liên quan. Khi dữ liệu nằm ở nhiều dịch vụ, phải thiết kế rõ nơi điều phối và cách bảo vệ trong khoảng trạng thái chưa đồng bộ.

Tương tự, một quyết định cho phép sửa tài liệu ở thời điểm T1 có thể dựa trên parent cũ. Nếu parent đổi ở T2 trước khi ghi nội dung, hệ thống cần cơ chế bảo đảm thao tác vẫn được ủy quyền theo mức nhất quán đã cam kết. Chỉ kiểm tra quyền một lần tại giao diện không giải quyết thay đổi này.

## 9. Thu hồi quyền, cache và tính nhất quán

### 9.1. Phạm vi phụ thuộc rộng hơn tài nguyên đích

Quyết định đọc một tài liệu có thể phụ thuộc vào grant trên thư mục gốc, membership của một nhóm và đường parent qua nhiều cấp. Cache chỉ theo `(user, document)` có thể giữ một kết luận cũ sau khi bất kỳ phụ thuộc nào thay đổi.

Những sự kiện có thể làm kết quả cũ mất hiệu lực gồm:

- Gỡ hoặc cấp grant ở bất kỳ ancestor có ảnh hưởng.
- Thay đổi membership của nhóm tham gia đường cấp quyền.
- Đổi parent của tài liệu hoặc một ancestor.
- Thay đổi điểm dừng kế thừa hay quy tắc kết hợp.
- Thay model permission hoặc trạng thái tenant, tài khoản, phiên.
- Thay trạng thái tài nguyên nếu trạng thái tham gia policy.

Chỉ tăng phiên bản của tài liệu đích khi sửa nội dung không đủ phản ánh việc một grant ở folder cha vừa bị thu hồi. Cần theo dõi hoặc đại diện được các phụ thuộc quyền liên quan.

### 9.2. Những cách quản lý dữ liệu dẫn xuất

Có thể cân nhắc các thiết kế sau, tùy quy mô và yêu cầu:

| Cách làm | Điểm cần kiểm soát |
| --- | --- |
| Đánh giá trên nguồn quan hệ có mức nhất quán phù hợp | Chi phí truy vấn và trạng thái mà nguồn thực sự bảo đảm |
| Cache kèm phụ thuộc và invalidation | Tác động từ ancestor, nhóm và thay đổi model |
| Dùng một authorization revision chung cho phạm vi | Làm mất cache rộng, khả năng tạo điểm nóng |
| Tính sẵn quyền hoặc quan hệ bao đóng | Cập nhật khi cấu trúc hoặc grant đổi, khoảng trễ thu hồi |
| TTL ngắn cùng kiểm tra bổ sung cho hành động nhạy cảm | TTL vẫn cho phép một khoảng dùng quyền cũ |

Một revision chỉ có ý nghĩa nếu mọi thay đổi liên quan đều cập nhật nó và các đường thực thi kiểm tra nó đúng cách. Đưa một số phiên bản vào khóa cache không tự tạo ra tính nhất quán.

Tài liệu [OpenFGA về query consistency](https://openfga.dev/docs/interacting/consistency) phân biệt truy vấn có thể dùng cache với lựa chọn bỏ qua cache của engine. Khi tích hợp một sản phẩm cụ thể, cần hiểu bảo đảm thực tế của chế độ đọc; một tùy chọn ở engine không tự vô hiệu hóa cache HTTP hoặc cache riêng của ứng dụng.

### 9.3. Thu hồi là yêu cầu cần có giới hạn rõ ràng

Nếu người quản trị gỡ quyền đọc ở folder, sản phẩm cần biết khi nào các tài liệu bên dưới ngừng cho phép theo đường đó. “Đã xóa grant trong database” và “mọi endpoint đã dừng dùng quyền cũ” là hai mốc khác nhau trong hệ thống phân tán.

Có thể dùng transactional outbox để bảo đảm thay đổi và sự kiện đồng bộ không bị tách rời do lỗi sau commit. Tuy nhiên, outbox không làm cho mọi bản sao và cache cập nhật nguyên tử. Cần xử lý khoảng trễ, sự kiện lặp, sự kiện sai thứ tự và thất bại ở consumer.

Đối với thao tác có cam kết thu hồi chặt, có thể cần kiểm tra nguồn chuẩn hoặc một mốc phiên bản mà hệ thống thực sự hỗ trợ, thay vì chờ TTL. Phương án phải bao phủ mọi endpoint có liên quan, không chỉ trang xem chi tiết.

Cache kết quả từ chối cũng cần được cập nhật khi cấp quyền mới. Nếu không, người dùng có thể tiếp tục bị chặn dù policy và quan hệ hiện tại đã cho phép. Lỗi không đọc được cấu trúc nên được phân biệt với một kết quả từ chối đã đánh giá đầy đủ.

### 9.4. Download, tìm kiếm và tác vụ chạy nền

Một người bị gỡ quyền kế thừa vẫn có thể còn một URL tải đã phát hành. Cần hiểu URL đó có kiểm tra quyền tại lúc dùng hay tự mang quyền trong thời gian hiệu lực. Đổi grant không tự thu hồi được mọi cơ chế phát hành trước đó.

Tìm kiếm, số lượng kết quả và tên tài liệu cũng có thể tiết lộ dữ liệu. Việc chỉ lọc quyền ở trang chi tiết không đủ nếu một API danh sách trả toàn bộ metadata của tài liệu không được phép.

Với tác vụ export chạy nền, quyết định ở thời điểm nhận yêu cầu có thể cũ vào lúc tạo hoặc giao kết quả. Cần quy định thời điểm đánh giá lại hoặc cơ chế ủy quyền giới hạn thời gian và phạm vi, cùng hành vi khi quyền gốc bị thu hồi.

Quyền truy cập nên được kiểm tra tại backend cho từng yêu cầu liên quan. Đây cũng là khuyến nghị của [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html#validate-the-permissions-on-every-request).

## 10. Giải thích quyết định và quản lý ngoại lệ

### 10.1. Lưu dấu vết của đường cấp quyền

Khi người quản trị hỏi vì sao Lan đọc được tài liệu, câu trả lời “allowed=true” thường chưa đủ. Một dấu vết hữu ích có thể cho biết:

```text
subject: user:lan
permission: read
target: document:budget-2026
source: inherited
path:
  document:budget-2026 -> folder:planning -> folder:hr
grant:
  user:lan viewer folder:hr
policyVersion: document-access-v5
authorizationRevision: rev-481
```

Đây là dữ liệu minh họa, không phải một response chuẩn của mọi engine. Nếu có nhiều đường cấp quyền, một đường giải thích được tìm thấy không chứng minh đó là đường duy nhất. Muốn xác nhận thu hồi hoàn toàn phải xét những đường khác mà policy cho phép.

Thông tin đường dẫn, tên thư mục và membership có thể nhạy cảm. API giải thích quyền cần được kiểm soát; người không được đọc thư mục cha không nên lấy được toàn bộ cấu trúc tổ chức chỉ bằng một endpoint debug.

### 10.2. Audit thay đổi quan hệ và policy

Khi grant hoặc parent thay đổi, có thể ghi actor, tenant, đối tượng, quan hệ cũ/mới, phiên bản, lý do và kết quả commit. Với thay đổi lớn, cần biết phạm vi ảnh hưởng để điều tra và khôi phục khi cần.

Audit của quyết định truy cập khác với audit thay đổi policy. Một bản ghi cho phép đọc không thể thay thế lịch sử ai đã chia sẻ thư mục; một bản ghi gỡ grant cũng không tự chứng minh endpoint đã dùng dữ liệu mới.

Không cần ghi token, bí mật phiên hoặc toàn bộ nội dung tài liệu. Tập dữ liệu lưu lại phải đủ phục vụ mục đích truy vết, có thời hạn và quyền truy cập thích hợp.

### 10.3. Kiểm soát số lượng ngoại lệ

Kế thừa giúp giảm số grant phải quản lý. Nếu mọi tài liệu con đều có nhiều quy tắc dừng, deny và grant riêng, người quản trị có thể khó dự đoán quyền hiệu lực.

Khi ngoại lệ quá nhiều, nên xem lại cách tổ chức tài nguyên hoặc ranh giới chia sẻ. Chia tài liệu theo các phạm vi truy cập ổn định thường dễ quản lý hơn một cây có cấu trúc chỉ phục vụ điều hướng nhưng lại bị dùng làm mô hình quyền không phù hợp.

## 11. Những lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Hướng xử lý |
| --- | --- | --- |
| Mặc định có parent là kế thừa mọi quyền | Quyền quản trị lan rộng ngoài ý định | Định nghĩa riêng permission được truyền |
| Coi quyền editor từ cha là ownership của con | Người sửa có thể chuyển owner hoặc chia sẻ sai | Tách quan hệ owner trực tiếp và permission suy ra |
| Gỡ grant trực tiếp rồi kết luận đã hết quyền | Bỏ sót đường kế thừa hoặc nhóm | Xét quyền hiệu lực và các đường còn lại |
| Dùng danh sách allow rỗng để biểu thị deny | Quyền từ cha vẫn có thể cho phép | Mô hình điểm dừng hoặc deny rõ ràng |
| Cho editor đổi `parentId` qua API nội dung | Tạo hoặc thay đổi đường cấp quyền | Permission riêng cho thay đổi cấu trúc |
| Chỉ kiểm tra parent mới thuộc cùng tenant khi tạo | Dữ liệu cập nhật có thể vượt ranh giới | Cưỡng chế ở mọi luồng ghi và bảo vệ đường đánh giá |
| Không phát hiện chu trình hoặc giới hạn công việc | Lặp vô hạn, tiêu tốn tài nguyên | Kiểm tra cấu trúc và trả lỗi an toàn khi không đánh giá được |
| Cache chỉ phụ thuộc phiên bản tài liệu | Không thấy thay đổi quyền ở ancestor | Theo dõi phụ thuộc quyền hoặc revision phù hợp |
| Sao chép ACL nhưng mô tả như kế thừa động | Thu hồi ở cha không thu hồi các bản sao | Công bố đúng hành vi và quản lý dữ liệu dẫn xuất |
| Bảo vệ trang chi tiết nhưng bỏ qua download hoặc list | Người gọi tiếp cận dữ liệu qua đường khác | Áp dụng permission cho từng đường thực thi |

## 12. Kiểm thử và bài tập vận dụng

### 12.1. Ma trận kiểm thử mô hình minh họa

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| Lan là viewer của hr, không có grant trực tiếp ở budget-2026 | Được đọc qua đường kế thừa khi các điều kiện khác đạt |
| Lan chỉ là viewer của hr và yêu cầu sửa tài liệu | Không được sửa từ nguồn quyền đó |
| Nam là editor của planning | Được đọc và sửa các tài liệu con theo model |
| Mai có viewer trực tiếp của budget-2026 | Được đọc tài liệu, không tự được đọc tài liệu anh em |
| Huy là owner của budget-2026 | Có quyền theo owner của tài liệu, không tự thành owner của planning |
| Người dùng có permission ở con nhưng không ở cha | Không tự có quyền liệt kê toàn bộ cha |
| Gỡ viewer ở hr nhưng giữ viewer trực tiếp trên tài liệu | Quyền đọc qua grant trực tiếp còn tồn tại |
| Gỡ mọi đường cấp quyền có liên quan | Không được phép sau khi dữ liệu quyền cập nhật theo cam kết |
| Parent thuộc tenant khác | Không dùng đường đó để cấp quyền |
| Parent không tồn tại trong snapshot mà đáng lẽ phải có | Không đánh giá thành công; không cấp quyền do lỗi dữ liệu |
| Parent là document trong model chỉ cho parent là folder | Cấu trúc không hợp lệ |
| Chuỗi parent có chu trình | Không lặp vô hạn; không trả allow vì chạm chu trình |
| Đường có 64 nút, gốc là nút cuối trong ví dụ Java | Có thể hoàn tất đánh giá |
| Đường cần nút thứ 65 trong ví dụ Java | Không xác định do giới hạn; không cho phép thao tác |
| Có grant trực tiếp nhưng ancestor bị vô hiệu hóa | Bị chặn theo quy tắc toàn chuỗi của ví dụ Java |
| Tài khoản hoặc phiên đã bị vô hiệu hóa | Không cho phép dù còn grant kế thừa |
| Tài liệu chuyển sang thư mục chia sẻ rộng | Tập quyền hiệu lực thay đổi theo đường mới |
| Hai thao tác đổi parent đồng thời có thể tạo chu trình | Bất biến cấu trúc phải được bảo vệ khi commit |
| Gỡ grant ở cha trong khi cache còn allow | Không được phá cam kết thu hồi của hệ thống |
| Thêm grant mới trong khi cache còn deny | Không tiếp tục chặn vượt giới hạn cập nhật đã quy định |

Nếu triển khai điểm dừng kế thừa, deny hoặc nhiều parent, cần bổ sung các trường hợp kết hợp cho đúng model mới. Không dùng kết quả của model đơn giản để suy ra hành vi của các tính năng chưa được triển khai.

Kiểm thử tích hợp cần gọi trực tiếp các endpoint với định danh tài nguyên khác nhau, không chỉ mô phỏng thao tác ở UI. Cũng cần kiểm tra sự cố đọc nguồn quan hệ và khoảng đồng bộ sau cấp hoặc thu hồi grant.

### 12.2. Bài tập thiết kế thư mục nhạy cảm

Trong một workspace, folder:company được chia sẻ cho mọi nhân viên. Folder:finance nằm bên dưới và chứa hai tài liệu: budget-summary có thể đọc rộng, còn salary-detail chỉ dành cho nhóm payroll. Ngoài ra, một kiểm toán viên ngoài nhóm cần đọc trực tiếp salary-detail trong thời gian giới hạn.

Hãy thiết kế model và trả lời:

1. Đặt ranh giới kế thừa ở đâu để salary-detail không tự mở cho mọi nhân viên?
2. Grant của kiểm toán viên là trực tiếp hay kế thừa, và thời hạn áp dụng tại đâu?
3. Người được sửa salary-detail có được di chuyển nó sang company không? Permission nào quyết định?
4. Nếu nhóm payroll bị gỡ khỏi finance, các đường đọc salary-detail nào vẫn có thể còn?
5. Khi thay parent hoặc thu hồi grant, những cache và tác vụ chạy nền nào cần xét lại quyền?
6. Dữ liệu giải thích quyết định nào đủ cho quản trị viên nhưng không làm lộ thông tin tổ chức cho người không có quyền?

Một thiết kế nhất quán phải làm rõ hướng truyền, permission được truyền, điểm dừng và quy tắc kết hợp. Khi những điều đó được thể hiện thành model có thể kiểm tra, quyền kế thừa giúp quản lý truy cập theo cấu trúc tài nguyên mà vẫn giữ được phạm vi và nguyên tắc ít quyền nhất.
