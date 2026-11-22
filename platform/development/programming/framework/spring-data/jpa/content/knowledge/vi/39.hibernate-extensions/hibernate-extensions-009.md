# Đánh giá chi phí phụ thuộc nhà cung cấp trước khi sử dụng

Spring Data JPA thường dùng Hibernate làm JPA provider. Hibernate có annotation riêng, API Session, HQL mở rộng, filter, custom type và batch fetching ngoài chuẩn Jakarta Persistence. Extension có thể giải quyết vấn đề thực tế nhưng tạo chi phí nâng cấp, kiểm thử, portability, vận hành và chuyển provider/database. Chỉ nên dùng khi lợi ích rõ ràng và phạm vi phụ thuộc được kiểm soát.

## 1. Nhận diện API

- **Jakarta Persistence:** EntityManager, JPQL, EntityGraph, LockModeType; chuẩn persistence.
- **Spring Data JPA:** JpaRepository, Specification, repository method; abstraction của Spring Data.
- **Hibernate:** Session, @BatchSize, @Formula, @Filter, HQL extension; phụ thuộc provider.
- **Database:** JSON function, partial index, SQL hint; phụ thuộc engine/version.

Dùng JpaRepository không đảm bảo portability nếu entity có annotation Hibernate hoặc query dùng cú pháp riêng. EntityGraph chuẩn JPA khác annotation @EntityGraph của Spring Data.

## 2. Chi phí vòng đời

API có thể deprecated hoặc đổi giữa major version; ưu tiên API public, documented, tránh internal/experimental. Spring Boot quản lý Hibernate theo dependency set; override riêng hibernate-core có thể gây xung đột. Session, HQL mở rộng, annotation Hibernate và native SQL làm tăng chi phí đổi provider/database. Lazy loading, filter, custom type, SQL và transaction cần integration test đúng provider/database. Extension có thể giảm query nhưng tải nhiều dữ liệu hoặc sinh SQL kém với cardinality khác. Nhóm cần hiểu debug, đọc SQL và nâng cấp.

Ước lượng entity, repository, query và module bị ảnh hưởng nếu loại bỏ extension. Chi phí tăng khi API provider rò rỉ vào domain service/controller.

## 3. Quy trình quyết định

1. Mô tả bottleneck/hành vi cần có; tách yêu cầu bắt buộc khỏi mong muốn tối ưu.
2. Kiểm tra Jakarta Persistence, JPQL, Criteria, EntityGraph, projection và Spring Data.
3. Đo baseline: SQL, số query, latency, dòng đọc, bộ nhớ và transaction.
4. Đọc tài liệu đúng version Hibernate/database; kiểm tra supported, deprecated và migration guide.
5. Benchmark dữ liệu đại diện, làm proof of concept và integration test.
6. Ước lượng chi phí nâng cấp/thoát, cô lập phạm vi và ghi quyết định.
7. Chọn extension khi lợi ích đo được lớn hơn chi phí vòng đời.

## 4. Ví dụ: batch fetching và N+1

Tải PurchaseOrder rồi truy cập collection lines có thể tạo N+1 query. Hibernate @BatchSize gom các lần tải association lazy theo nhóm:

~~~java
@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
@BatchSize(size = 32)
private List<OrderLine> lines;
~~~

Số query phụ thuộc entity truy cập, session state, batch size và version. So sánh với EntityGraph chuẩn JPA, JPQL fetch join hoặc DTO projection. Spring Data @EntityGraph tích hợp graph vào repository; fetch nhiều collection có thể nhân bản dòng hoặc gây vấn đề pagination. Kiểm tra SQL và benchmark database thật.

## 5. Ví dụ: @Formula và Session

Hibernate @Formula ánh xạ biểu thức SQL vào thuộc tính entity. Biểu thức có thể xuất hiện mỗi lần tải entity, subquery tốn kém và cú pháp phụ thuộc database. Thay thế bằng DTO projection, JPQL aggregate, GROUP BY, view hoặc generated column.

EntityManager là API chuẩn. Khi cần Hibernate, có thể unwrap Session:

~~~java
Session session = entityManager.unwrap(Session.class);
session.setDefaultReadOnly(true);
~~~

Giữ Session trong adapter/custom repository fragment; không đưa vào controller, domain service hoặc public interface. Truy vấn thường nên dùng JPQL/EntityManager hoặc repository.

## 6. Giảm lock-in và kiểm thử

Đặt annotation Hibernate trong module persistence; đưa Session, Filter, custom type và HQL riêng vào adapter. Trả entity/projection/DTO ứng dụng; không để Hibernate-specific type thoát ra service API. H2 không chứng minh dialect, locking, kiểu dữ liệu hoặc SQL giống PostgreSQL/MySQL; dùng Testcontainers với engine/version gần production. Với Spring Boot, ưu tiên dependency management của Boot; trước major upgrade đọc migration guide Hibernate và chạy integration/performance tests.

## 7. ADR và checklist

Ghi ADR: vấn đề, giải pháp chuẩn đã cân nhắc, extension được chọn, lợi ích đo được, rủi ro, module phụ thuộc, version hỗ trợ và phương án thay thế. Lỗi thường gặp: dùng extension trước khi đo bottleneck; nghĩ Hibernate mặc định là portable; rải Session; native SQL không ghi rõ database; chỉ test H2; override Hibernate ngoài dependency management; không có kế hoạch loại bỏ.

- [ ] Đã phân biệt Jakarta Persistence, Spring Data, Hibernate và database.
- [ ] Đã xem xét JPQL, EntityGraph, projection hoặc giải pháp chuẩn.
- [ ] Đã đọc tài liệu và trạng thái hỗ trợ đúng version.
- [ ] Đã đánh giá chi phí nâng cấp, chuyển provider/database, test và vận hành.
- [ ] Đã đo baseline và kết quả trên dữ liệu đại diện.
- [ ] Extension được giới hạn trong persistence layer/adapter.
- [ ] Có integration test đúng database và kế hoạch nâng cấp.
- [ ] Có ADR ghi lý do, giới hạn và phương án thay thế.

Dùng Jakarta Persistence và Spring Data khi đáp ứng yêu cầu; chọn extension Hibernate khi lợi ích được kiểm chứng, API được hỗ trợ và phạm vi phụ thuộc được kiểm soát.