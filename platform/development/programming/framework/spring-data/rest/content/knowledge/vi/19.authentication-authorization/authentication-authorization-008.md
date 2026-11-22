# Kiểm soát truy cập theo chủ sở hữu và ngăn truy cập chéo bản ghi

## Mục tiêu

Xác thực (authentication) xác định người đang gọi API; phân quyền (authorization) quyết định người đó được phép làm gì với từng bản ghi. Với API expose qua Spring Data REST, chỉ yêu cầu đăng nhập hoặc kiểm tra role chung là chưa đủ: người dùng A không được đọc, sửa, xóa hoặc liên kết đến bản ghi thuộc người dùng B nếu nghiệp vụ không cho phép.

Rủi ro thường gặp là IDOR/BOLA (Insecure Direct Object Reference / Broken Object Level Authorization): client thay ID trong URL, ví dụ từ `/api/orders/42` thành `/api/orders/43`, rồi truy cập bản ghi của người khác. ID khó đoán hoặc UUID không thay thế kiểm tra quyền ở server.

## Mô hình hóa chủ sở hữu

Đưa quan hệ chủ sở hữu vào model dữ liệu và xác định rõ bản ghi thuộc về user hay tenant nào. Ví dụ:

    @Entity
    public class Order {
        @Id
        @GeneratedValue
        private Long id;

        @ManyToOne(fetch = FetchType.LAZY, optional = false)
        @JoinColumn(name = "owner_id", nullable = false, updatable = false)
        private User owner;

        private String description;

        // getters and business methods
    }

`owner_id` là dữ liệu phân quyền quan trọng. Nếu quyền truy cập dựa trên tenant, lưu tenant association hoặc tenant key tương ứng và dùng nó trong mọi truy vấn. Với hệ thống cho phép chia sẻ bản ghi, mô hình thêm bảng quyền/chia sẻ thay vì giả định chỉ một owner mới được truy cập.

Không nhận owner từ dữ liệu do client tự gửi. Khi tạo bản ghi, lấy user đã xác thực từ `SecurityContext` hoặc một `CurrentUser` service rồi gán owner ở phía server. Có thể dùng DTO đầu vào không có trường `ownerId`; nếu expose entity trực tiếp, cấu hình property owner chỉ đọc hoặc không export association đó. `updatable = false` giúp khóa cập nhật cột ở JPA, nhưng không thay thế kiểm tra quyền và kiểm soát binding request.

## Authentication và URL authorization

Cấu hình Spring Security để endpoint yêu cầu danh tính đã xác thực và bật method security cho service:

    @Configuration
    @EnableMethodSecurity
    public class SecurityConfiguration {
        @Bean
        SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
            return http
                .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/api/**").authenticated()
                    .anyRequest().permitAll())
                .build();
        }
    }

Quy tắc URL trên chỉ yêu cầu đăng nhập cho `/api/**`. Nó chưa chứng minh người gọi sở hữu bản ghi có ID trong URL. Kiểm tra theo role như `hasRole('USER')` cũng không đủ nếu mọi user cùng role nhưng mỗi người chỉ được xem dữ liệu của mình.

## Lọc bản ghi ngay trong truy vấn

Đối với collection, lọc theo owner trong database trước khi phân trang. Ví dụ repository:

    public interface OrderRepository extends JpaRepository<Order, Long> {
        Page<Order> findAllByOwnerId(Long ownerId, Pageable pageable);

        Optional<Order> findByIdAndOwnerId(Long id, Long ownerId);
    }

Service lấy owner ID từ danh tính đã xác thực và dùng các truy vấn có scope:

    @Service
    public class OrderAccessService {
        private final OrderRepository orders;
        private final CurrentUser currentUser;

        public OrderAccessService(OrderRepository orders,
                                  CurrentUser currentUser) {
            this.orders = orders;
            this.currentUser = currentUser;
        }

        @PreAuthorize("isAuthenticated()")
        public Page<Order> listMine(Pageable pageable) {
            return orders.findAllByOwnerId(
                currentUser.requireUserId(), pageable);
        }

        @PreAuthorize("isAuthenticated()")
        public Order getMine(Long id) {
            return orders.findByIdAndOwnerId(
                    id, currentUser.requireUserId())
                .orElseThrow(() -> new NotFoundException());
        }
    }

`CurrentUser` là service của ứng dụng đọc principal đã xác thực và ánh xạ nó sang user ID nội bộ. Không lấy `ownerId` từ query parameter hoặc request body rồi truyền thẳng vào repository.

Truy vấn `findAllByOwnerId` bảo đảm lọc diễn ra trước `LIMIT/OFFSET`, nên metadata phân trang phản ánh đúng tập bản ghi mà user được phép xem. Tránh tải tất cả bản ghi rồi dùng `@PostFilter` để loại bản ghi của người khác: cách đó tốn tài nguyên, có thể làm sai tổng số trang và dễ để lộ thông tin qua metadata.

## Kết hợp với Spring Data REST

Repository được Spring Data REST export tự động thường cung cấp collection, item và association endpoint. Cần bảo vệ từng loại đường dẫn:

- **Collection GET:** chỉ trả các bản ghi thuộc owner/tenant hiện tại.
- **Item GET:** chỉ trả bản ghi mà người gọi được phép đọc.
- **POST:** server tự gán owner từ principal; không chấp nhận owner do client chỉ định.
- **PUT/PATCH:** xác minh owner của bản ghi đã lưu trước khi áp dụng thay đổi; ngăn request chuyển owner sang người gọi.
- **DELETE:** kiểm tra quyền trên bản ghi đã lưu trước khi xóa.
- **Association PUT/POST/DELETE:** kiểm tra quyền trên cả resource nguồn và resource đích, cùng quy tắc chia sẻ hoặc tenant.

Spring Data REST repository event handlers như `@HandleBeforeCreate`, `@HandleBeforeSave`, `@HandleBeforeDelete`, `@HandleBeforeLinkSave` và `@HandleBeforeLinkDelete` hữu ích để kiểm tra các thao tác ghi qua endpoint REST. Ví dụ:

    @Component
    @RepositoryEventHandler(Order.class)
    public class OrderOwnerHandler {
        private final CurrentUser currentUser;
        private final OrderOwnershipLookup ownership;

        public OrderOwnerHandler(CurrentUser currentUser,
                                 OrderOwnershipLookup ownership) {
            this.currentUser = currentUser;
            this.ownership = ownership;
        }

        @HandleBeforeCreate
        public void beforeCreate(Order order) {
            order.setOwner(currentUser.requireUser());
        }

        @HandleBeforeSave
        public void beforeSave(Order incoming) {
            Long storedOwnerId = ownership.requireOwnerId(incoming.getId());
            currentUser.requireOwnerOrAdmin(storedOwnerId);
            if (!storedOwnerId.equals(incoming.getOwner().getId())) {
                throw new AccessDeniedException("Owner cannot be changed.");
            }
        }

        @HandleBeforeDelete
        public void beforeDelete(Order storedOrder) {
            currentUser.requireOwnerOrAdmin(storedOrder.getOwner().getId());
        }
    }

`OrderOwnershipLookup` nên đọc owner ID đã lưu bằng một truy vấn chuyên biệt. Khi kiểm tra update, không chỉ kiểm tra `incoming.getOwner()`: payload có thể đã thay owner trước khi handler chạy. Phải so sánh với owner trong database và từ chối việc chuyển quyền sở hữu ngoài luồng nghiệp vụ được phép.

**Giới hạn quan trọng:** REST event handler không bảo vệ request GET và không tự lọc collection. Nếu chỉ thêm `@HandleBeforeSave`/`@HandleBeforeDelete`, user vẫn có thể đọc bản ghi người khác hoặc thấy chúng trong danh sách. Cần bảo vệ read path bằng method security/query scope hoặc thay endpoint tự động bằng endpoint có kiểm soát.

## Khi cần bảo đảm owner-scope cho toàn bộ API

Nếu không thể chứng minh mọi collection, item và association endpoint tự động đều được lọc theo người gọi, hãy tắt export repository và cung cấp controller/service có kiểm soát:

    @RepositoryRestResource(exported = false)
    public interface OrderRepository extends JpaRepository<Order, Long> {
        Page<Order> findAllByOwnerId(Long ownerId, Pageable pageable);
        Optional<Order> findByIdAndOwnerId(Long id, Long ownerId);
    }

Controller gọi `OrderAccessService` thay vì gọi `findAll()` hoặc `findById()` không có scope. Ví dụ:

    @RestController
    @RequestMapping("/api/orders")
    public class OrderController {
        private final OrderAccessService access;

        public OrderController(OrderAccessService access) {
            this.access = access;
        }

        @GetMapping
        public Page<Order> list(Pageable pageable) {
            return access.listMine(pageable);
        }

        @GetMapping("/{id}")
        public Order get(@PathVariable Long id) {
            return access.getMine(id);
        }
    }

Áp dụng cùng nguyên tắc cho create, update, delete và association: controller nhận request, service xác định principal, truy vấn bản ghi trong scope và thực hiện nghiệp vụ trong transaction. Không để một đường dẫn Spring Data REST mặc định khác vẫn expose repository không lọc.

Nếu vẫn giữ repository export, hãy kiểm tra cụ thể cách Spring Data REST gọi từng repository method trong phiên bản đang dùng. Method security trên `findById` có thể giúp bảo vệ item lookup, nhưng không tự biến `findAll(Pageable)` thành truy vấn owner-scoped. Một search method riêng có filter không bảo vệ collection root nếu root vẫn trả dữ liệu toàn cục.

## Bảo vệ association và ngăn liên kết chéo

Kiểm tra quyền của cả hai đầu association. Ví dụ user A sở hữu `Order/42` nhưng cố gắng gắn vào `Customer/99` thuộc tenant B. Chỉ kiểm tra owner của order là chưa đủ; service phải xác minh customer cũng nằm trong phạm vi mà user được phép liên kết.

Quy tắc có thể gồm:

- Resource nguồn thuộc user hiện tại hoặc user có role quản trị phù hợp.
- Resource đích thuộc cùng tenant hoặc được chia sẻ rõ ràng với người gọi.
- Loại association và trạng thái nghiệp vụ cho phép liên kết.
- Không cho phép gán một resource đích chỉ vì client biết URI hoặc ID của nó.
- Khi gỡ liên kết, xác minh quyền thay đổi association; không nhầm xóa link với xóa entity đích.

Với association REST, dùng `@HandleBeforeLinkSave`/`@HandleBeforeLinkDelete` để kiểm tra luồng REST nếu repository vẫn được export. Với controller tùy chỉnh, thực hiện cùng kiểm tra trong service. Đưa quy tắc dùng chung vào service/domain layer để không phụ thuộc duy nhất vào REST event.

## Phân quyền quản trị và chia sẻ

Nếu admin được phép xem mọi bản ghi, thể hiện nhánh này rõ trong service/query thay vì nới lỏng kiểm tra ở nhiều nơi. Ví dụ service có thể chọn truy vấn theo owner cho user thường và truy vấn toàn cục chỉ sau khi xác nhận role quản trị.

Nếu một bản ghi có nhiều người được phép truy cập, mô hình hóa ACL hoặc bảng chia sẻ (record, user, permission). Truy vấn đọc và ghi phải kiểm tra quyền tương ứng như `READ`, `UPDATE`, `DELETE`, `LINK`. Không coi việc biết URL hoặc có liên kết HAL là bằng chứng được cấp quyền.

Đối với multi-tenant, thêm tenant ID vào điều kiện truy vấn cùng owner hoặc ACL. Mọi đường đọc và ghi phải có tenant scope; không chỉ kiểm tra tenant ở giao diện hoặc khi tạo bản ghi.

## Phản hồi khi không có quyền

Khi ID không thuộc người gọi, API có thể trả `404 Not Found` để không tiết lộ bản ghi có tồn tại hay không, hoặc `403 Forbidden` nếu chính sách cho phép tiết lộ sự tồn tại. Chọn một cách nhất quán cho từng API và không trả dữ liệu owner, tenant hoặc nội dung bản ghi trong lỗi.

Truy vấn `findByIdAndOwnerId(...).orElseThrow(NotFoundException)` là cách thường dùng để che giấu sự tồn tại của bản ghi ngoài phạm vi. Nếu ứng dụng dùng `403`, hãy bảo đảm response không tiết lộ trường nhạy cảm. Với người chưa đăng nhập, trả `401 Unauthorized` theo cơ chế authentication.

## Các lỗi thiết kế cần tránh

- Chỉ yêu cầu đăng nhập hoặc role `USER` rồi cho phép truy cập mọi ID.
- Tin `ownerId`, `tenantId` hoặc user ID gửi trong JSON/query parameter.
- Chỉ kiểm tra quyền ở UI hoặc dựa vào ID khó đoán/UUID.
- Dùng REST event để bảo vệ GET hoặc lọc collection; các event ghi không bao phủ read path.
- Lấy bản ghi toàn cục rồi mới kiểm tra hoặc lọc trong bộ nhớ.
- Kiểm tra owner trên entity đã được bind từ request mà không đối chiếu owner đã lưu.
- Cho phép update owner qua PUT/PATCH thông thường.
- Kiểm tra resource nguồn nhưng bỏ qua quyền trên resource đích của association.
- Dùng cache có key chỉ theo record ID khi response phụ thuộc user/tenant; cache key phải bao gồm phạm vi quyền hoặc dữ liệu đã được lọc đúng.

## Kiểm tra bằng integration test

Tạo ít nhất hai user độc lập, A và B, mỗi người có bản ghi riêng. Gửi request HTTP qua đúng endpoint mà ứng dụng expose và kiểm tra:

1. User A chỉ thấy bản ghi của A trong collection; phân trang và `totalElements` cũng chỉ tính bản ghi của A.
2. User A GET item của B bằng cách thay ID trong URL; response là 404 hoặc 403 theo chính sách và không chứa dữ liệu B.
3. User A PUT/PATCH item của B; request bị từ chối và database không thay đổi.
4. User A DELETE item của B; request bị từ chối và bản ghi vẫn còn.
5. User A POST bản ghi với `ownerId` của B trong payload; server bỏ qua hoặc từ chối trường đó và owner lưu là A.
6. User A PUT/PATCH cố đổi owner của bản ghi A thành B; request bị từ chối và owner trong database vẫn là A.
7. User A gắn bản ghi A với resource đích thuộc tenant B; association bị từ chối.
8. User A không thể gỡ association mà mình không có quyền quản lý.
9. Admin thực hiện đúng các thao tác toàn cục theo chính sách.
10. Request không xác thực nhận 401; request đã xác thực nhưng không có quyền nhận 403/404 theo chính sách.

Kiểm tra cả status code lẫn trạng thái database sau mỗi request thất bại. Test collection cần xác nhận không có bản ghi chéo trong body, embedded links, tổng số phần tử hoặc metadata phân trang. Nếu dùng cache, chạy test sau khi một user đã đọc dữ liệu để bảo đảm response không bị trả nhầm cho user khác.

## Quy trình triển khai

1. Xác định owner/tenant và các quy tắc chia sẻ trong model.
2. Lấy danh tính và owner ID từ principal đã xác thực; không tin dữ liệu owner do client gửi.
3. Viết repository query lọc theo owner/tenant trước khi phân trang.
4. Đưa kiểm tra quyền đọc, sửa, xóa và liên kết vào service dùng chung, bật method security.
5. Nếu repository export tự động không thể bảo đảm mọi read path được scope, đặt `exported = false` và dùng controller/service có kiểm soát.
6. Nếu vẫn dùng repository REST, bổ sung event handler cho create/save/delete/link nhưng đồng thời bảo vệ item GET và collection GET riêng.
7. Kiểm tra cả resource nguồn và đích khi thay association.
8. Giữ owner bất biến trong request update; dùng database constraint và transaction cho tính toàn vẹn.
9. Viết integration test với ít nhất hai user/tenant để thử IDOR, owner tampering và cross-link.

Kiểm soát truy cập theo chủ sở hữu phải được thực hiện ở server trên từng bản ghi và từng association. Authentication xác định ai đang gọi; truy vấn owner-scoped và authorization quyết định họ được đọc hoặc thay đổi dữ liệu nào. REST event hỗ trợ kiểm tra thao tác ghi qua Spring Data REST, còn read path và collection phải được bảo vệ riêng.