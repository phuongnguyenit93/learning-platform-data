# Phân biệt kiểm thử Repository, cấu hình xuất REST và hợp đồng HTTP trong Spring Data REST

Spring Data REST tự động xuất các Spring Data repository thành tài nguyên REST qua Spring MVC. Vì vậy, một bài kiểm thử repository chạy xanh chỉ chứng minh lớp truy cập dữ liệu hoạt động; nó chưa chứng minh repository được xuất đúng, URL được cấu hình đúng hoặc client nhận được HTTP response đúng hợp đồng.

Khi thiết kế bộ kiểm thử, hãy tách ba câu hỏi:

1. Repository có đọc, ghi và truy vấn dữ liệu đúng không?
2. Spring Data REST có phát hiện và xuất đúng repository, đường dẫn, query method và HTTP method không?
3. Client có nhận đúng status, header, media type, HAL link và dữ liệu qua HTTP không?

Ba nhóm có thể dùng chung dữ liệu mẫu, nhưng mỗi nhóm bảo vệ một ranh giới khác nhau.

## 1. Ma trận chọn loại kiểm thử

| Phạm vi | Điều cần chứng minh | Cách kiểm thử phù hợp |
|---|---|---|
| Repository | Mapping, CRUD, derived query, custom query, phân trang/sắp xếp và hành vi của database | Test slice của Spring Data, ví dụ `@DataJpaTest` |
| Cấu hình xuất REST | Repository có được export hay không; collection path/rel; base path; search endpoint; method exposure; projection và cấu hình `RepositoryRestConfigurer` | Khởi động application context thật bằng `@SpringBootTest`, gửi request bằng `MockMvc` |
| Hợp đồng HTTP | URL, HTTP method, status, request/response headers, media type, JSON/HAL body, link, paging, validation, ETag và security | `MockMvc` cho kiểm thử MVC tích hợp; `WebTestClient` hoặc HTTP client tới server thật cho end-to-end |

Không dùng một loại test thay cho cả ba. Ví dụ, repository có thể lưu được dữ liệu trong khi endpoint bị 404 vì repository không được export. Ngược lại, endpoint GET có thể trả 200 nhưng query method vẫn truy vấn sai dữ liệu.

## 2. Kiểm thử repository

### Mục tiêu và phạm vi

Repository test tập trung vào tầng persistence:

- Lưu, đọc, cập nhật và xóa entity.
- Derived query như `findByTitleContainingIgnoreCase`, custom query và tham số truy vấn.
- Quan hệ entity, cascade, lazy loading, mapping cột và ràng buộc dữ liệu.
- Kết quả khi không tìm thấy bản ghi, dữ liệu trùng hoặc đầu vào vi phạm constraint.
- Phân trang và sắp xếp ở repository khi repository hỗ trợ các abstraction tương ứng.

Với Spring Data JPA trong Spring Boot, `@DataJpaTest` là lựa chọn mặc định cho nhóm này. Test slice quét entity và cấu hình Spring Data JPA repository; nếu classpath có embedded database thì Boot có thể cấu hình database đó. Test thường chạy trong transaction và rollback sau mỗi test. `TestEntityManager` hữu ích khi cần chuẩn bị entity trực tiếp.

Ví dụ dưới đây giả định dự án đã có entity `Book` và repository `BookRepository` với phương thức `findByTitleContainingIgnoreCase`:

```java
@DataJpaTest
class BookRepositoryTest {

    @Autowired
    private BookRepository books;

    @Test
    void findsBooksByTitleIgnoringCase() {
        books.saveAndFlush(new Book("Spring Data REST"));

        assertThat(books.findByTitleContainingIgnoreCase("rest"))
            .extracting(Book::getTitle)
            .containsExactly("Spring Data REST");
    }
}
```

Test này chứng minh truy vấn repository trả đúng dữ liệu. Nó không khởi chạy toàn bộ Spring Data REST exporter và không chứng minh URL `/books` tồn tại.

Nếu cần kiểm tra hành vi phụ thuộc database production như dialect, constraint, kiểu dữ liệu hoặc native query, hãy chạy thêm test với đúng database. Với Boot, có thể dùng `@AutoConfigureTestDatabase(replace = Replace.NONE)` cùng Testcontainers hoặc database test đã cấu hình. Embedded database phù hợp cho test nhanh, nhưng không thay thế kiểm thử tương thích database thật.

Nếu dùng Spring Data module khác, chọn test slice tương ứng, chẳng hạn `@DataMongoTest`, `@DataJdbcTest` hoặc `@DataR2dbcTest`. Không dùng `@DataJpaTest` cho repository thuộc store khác.

## 3. Kiểm thử cấu hình xuất repository thành REST resource

### Những cấu hình cần bảo vệ

Spring Data REST quyết định repository nào được xuất bằng `RepositoryDetectionStrategy`. Các chiến lược có ý nghĩa sau:

- `DEFAULT`: xuất repository public hoặc repository được đánh dấu `@RepositoryRestResource`, miễn là `exported` không phải `false`.
- `ALL`: xuất mọi Spring Data repository, không phụ thuộc visibility hoặc annotation.
- `VISIBILITY`: chỉ xuất repository public, không phụ thuộc annotation.
- `ANNOTATED`: chỉ xuất repository có `@RepositoryRestResource` và không bị đặt `exported = false`.

Ngoài chiến lược phát hiện, hãy kiểm tra các điểm sau:

- Tên path và collection relation có đúng như API công bố không.
- Base path có được áp dụng không.
- Repository nội bộ có bị xuất ngoài ý muốn không.
- Query method có xuất hiện tại search resource không.
- Phương thức CRUD nào được phép gọi qua HTTP.
- Projection, association link và cấu hình tùy biến có được nạp trong application context không.

Ví dụ khai báo repository với path và search endpoint rõ ràng:

```java
@RepositoryRestResource(
    path = "books",
    collectionResourceRel = "books"
)
public interface BookRepository extends JpaRepository<Book, Long> {

    @RestResource(path = "by-title", rel = "by-title")
    List<Book> findByTitleContainingIgnoreCase(@Param("q") String q);
}
```

Search method ở ví dụ trên được công bố qua đường dẫn dạng `/books/search/by-title?q=...`. Đường dẫn collection mặc định còn có thể được tùy chỉnh bằng `@RepositoryRestResource`; đừng giả định tên pluralize nếu dự án đã đặt path riêng.

Có thể ẩn hoàn toàn repository bằng `@RepositoryRestResource(exported = false)`. Có thể ẩn một method khỏi REST exporter bằng `@RestResource(exported = false)`, ví dụ khi ứng dụng vẫn cần method đó cho xử lý nội bộ. Với các quy tắc HTTP method rộng hơn, dùng `RepositoryRestConfiguration.getExposureConfiguration()` trong `RepositoryRestConfigurer`.

Ví dụ đặt chiến lược chỉ export repository có annotation:

```java
@Configuration
class RestExposureConfiguration implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config,
            CorsRegistry cors) {

        config.setRepositoryDetectionStrategy(
            RepositoryDetectionStrategy.RepositoryDetectionStrategies.ANNOTATED
        );
    }
}
```

### Test cấu hình bằng application context thật

Để kiểm tra exporter, hãy tải cấu hình ứng dụng thật. Cách phổ biến là `@SpringBootTest` kết hợp `@AutoConfigureMockMvc`. Ví dụ kiểm tra collection relation ở root resource:

```java
@SpringBootTest
@AutoConfigureMockMvc
class RepositoryExposureTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void publishesBooksCollection() throws Exception {
        mvc.perform(get("/api").accept("application/hal+json"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$._links.books.href").exists());
    }

    @Test
    void doesNotPublishInternalNotes() throws Exception {
        mvc.perform(get("/api/internal-notes")
                .accept("application/hal+json"))
            .andExpect(status().isNotFound());
    }
}
```

Trong ví dụ, `/api` là base path giả định. Nếu ứng dụng không cấu hình base path thì dùng root path `/`; nếu repository có path hoặc relation khác, cập nhật URL và tên link theo cấu hình thực tế. Test endpoint không được export nên dùng path đã biết và không bị controller khác chiếm dụng.

Đây là test cấu hình export vì nó xác minh kết quả sau khi Spring nạp repository, annotation và `RepositoryRestConfigurer`. Một test chỉ khởi tạo object config hoặc chỉ kiểm tra annotation bằng reflection không chứng minh endpoint thực sự được đăng ký.

## 4. Kiểm thử hợp đồng HTTP

### Hợp đồng cần xác minh

Hãy kiểm tra response như một client bên ngoài nhìn thấy, thay vì chỉ kiểm tra method nội bộ đã chạy:

- **URL và link:** collection, item, search, association, self link và các link điều hướng.
- **HTTP method:** GET/POST trên collection; GET/PUT/PATCH/DELETE trên item nếu repository và cấu hình cho phép.
- **Status:** 200 cho đọc thành công; 201 và Location khi tạo tài nguyên thành công; 404 khi resource không tồn tại hoặc không được export; 405 khi method không được hỗ trợ; các status validation/security theo cấu hình ứng dụng.
- **Header và media type:** Accept, Content-Type, Location, ETag, Cache-Control nếu có và header bảo mật liên quan.
- **Body:** trường dữ liệu, kiểu dữ liệu, nullability, lỗi validation và cấu trúc HAL.
- **Phân trang/sắp xếp:** metadata page, link next/prev, tham số page/size/sort.
- **Điều kiện cập nhật:** ETag, If-Match, If-None-Match và status 412/304 khi phù hợp.

Spring Data REST thường biểu diễn hypermedia bằng HAL JSON. Khi kiểm tra link, gửi Accept rõ ràng là `application/hal+json`, rồi xác minh relation trong `_links`; không nên chỉ assert một chuỗi JSON lớn vì thứ tự field hoặc URL host có thể thay đổi.

Ví dụ kiểm tra response collection, media type và phân trang:

```java
@SpringBootTest
@AutoConfigureMockMvc
class BookHttpContractTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void returnsHalCollectionWithPagingMetadata() throws Exception {
        mvc.perform(get("/api/books")
                .param("size", "2")
                .accept("application/hal+json"))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.parseMediaType("application/hal+json")))
            .andExpect(jsonPath("$._links.self.href").exists())
            .andExpect(jsonPath("$.page.size").value(2));
    }

    @Test
    void rejectsDeleteOnCollection() throws Exception {
        mvc.perform(delete("/api/books"))
            .andExpect(status().isMethodNotAllowed());
    }
}
```

Assertion `$.page.size` giả định repository hỗ trợ paging. Nếu dự án đổi base path hoặc collection path, hãy thay URL theo cấu hình. Theo mặc định, collection resource hỗ trợ GET và POST; method khác trên collection trả 405. Item resource thường hỗ trợ GET, PUT, PATCH và DELETE, trừ khi repository method hoặc exposure configuration tắt chúng.

Ví dụ kiểm tra tạo resource:

```java
@Test
void createsBookAndReturnsLocation() throws Exception {
    mvc.perform(post("/api/books")
            .contentType(MediaType.APPLICATION_JSON)
            .accept("application/hal+json")
            .content("""
                {"title":"Spring Data REST"}
                """))
        .andExpect(status().isCreated())
        .andExpect(header().exists("Location"));
}
```

Body JSON phải khớp các trường có thể ghi của entity/projection thực tế. Nếu entity có validation hoặc quan hệ bắt buộc, hãy chuẩn bị payload hợp lệ theo model của ứng dụng.

### ETag và cập nhật có điều kiện

Nếu entity có trường version được đánh dấu bằng `@Version`, Spring Data REST có thể trả ETag tương ứng với phiên bản resource. Client có thể gửi ETag đó trong header `If-Match` khi PUT, PATCH hoặc DELETE. Nếu resource đã được client khác cập nhật, ETag cũ không còn khớp và server trả 412 Precondition Failed.

Nên có test xác minh hai tình huống: cập nhật với ETag hiện tại thành công; cập nhật với ETag cũ bị từ chối. Test phải lấy ETag từ response GET và giữ đúng URI của resource. Với GET có `If-None-Match`, response có thể là 304 Not Modified khi representation chưa thay đổi.

### MockMvc hay server thật?

- `MockMvc` chạy đầy đủ xử lý Spring MVC bằng request/response giả lập, không cần khởi động servlet container. Đây là lựa chọn nhanh cho phần lớn test export và HTTP contract.
- `@SpringBootTest(webEnvironment = RANDOM_PORT)` khởi động server thật trên cổng ngẫu nhiên. Kết hợp HTTP client hoặc `WebTestClient.bindToServer()` để kiểm tra đường đi end-to-end.
- `WebTestClient` cũng có thể gắn với mock server; với Spring MVC có thể dùng cầu nối MockMvc. Chọn cấu hình bind rõ ràng để biết test đang chạy mock hay server thật.

MockMvc không kiểm tra toàn bộ hành vi của server/container, context path thực tế, proxy, TLS hoặc cấu hình mạng. Vì vậy, giữ một số ít end-to-end test cho các luồng quan trọng. Nếu test dùng RANDOM_PORT/DEFINED_PORT, request từ client và xử lý trên server chạy ở hai thread/transaction khác nhau; transaction rollback của test không tự rollback thao tác đã commit trên server. Hãy dùng database cô lập hoặc dọn dữ liệu sau test.

## 5. Bộ test nên tổ chức thế nào?

Một cấu trúc thực tế có thể gồm:

| Nhóm test | Số lượng tương đối | Ví dụ kiểm tra |
|---|---:|---|
| Repository | Nhiều, chạy nhanh | Derived query, mapping, constraint, paging và sorting |
| Export configuration | Ít nhưng có mục tiêu | Repository được/không được export, base path, custom path, search rel, method bị ẩn |
| HTTP contract với MockMvc | Vừa phải | GET/POST/PATCH/DELETE, status, header, HAL link, validation, paging |
| End-to-end với server thật | Ít, tập trung | Luồng tạo/đọc/cập nhật quan trọng, security filter, context path và môi trường triển khai |

Giữ fixture nhỏ và độc lập. Mỗi test nên tạo dữ liệu cần dùng, không phụ thuộc thứ tự chạy hoặc dữ liệu còn lại từ test khác. Dùng identifier được trả về từ POST/GET thay vì hard-code ID do database sinh. Với HAL, ưu tiên kiểm tra relation và theo link; tránh khóa cứng host, port hoặc toàn bộ href tuyệt đối.

Về dependency, hãy dùng test artifact do đúng phiên bản Spring Boot quản lý. Boot 3 thường dùng `spring-boot-starter-test`; Boot 4 tách các test module theo chức năng, ví dụ `spring-boot-data-jpa-test` và `spring-boot-webmvc-test`. Không trộn import hoặc version từ các major khác nhau; để Spring Boot BOM quản lý version tương thích.

## 6. Troubleshooting

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| Repository test xanh nhưng GET collection trả 404 | Test chỉ tải JPA slice; repository không được export; sai base path hoặc path | Chạy `@SpringBootTest` với MockMvc; kiểm tra detection strategy, visibility, `exported`, `@RepositoryRestResource` và base path |
| Repository không xuất hiện ở root HAL | Detection strategy là ANNOTATED nhưng repository thiếu annotation; relation đã đổi | Kiểm tra `RepositoryDetectionStrategy`, `collectionResourceRel` và link trong response root |
| Request trả 405 | Method không được hỗ trợ hoặc đã bị ẩn | Kiểm tra repository có method CRUD tương ứng không, `@RestResource(exported = false)` và `ExposureConfiguration` |
| Test không thấy `_links` | Client đang yêu cầu JSON thường hoặc endpoint không phải SDR resource | Gửi `Accept: application/hal+json`; kiểm tra Content-Type và endpoint |
| Test phân trang không thấy `page` | Repository/query method không trả kiểu hỗ trợ paging hoặc test gọi nhầm endpoint | Kiểm tra `PagingAndSortingRepository`, `Pageable`, kiểu trả về `Page`/`Slice` và tham số `size` |
| MockMvc xanh nhưng gọi server thật thất bại | MockMvc không khởi động container; khác biệt context path, filter, proxy hoặc cấu hình server | Thêm test RANDOM_PORT/WebTestClient tới server thật và kiểm tra cấu hình triển khai |
| Dữ liệu từ test HTTP còn lại trong database | Server xử lý request ở transaction khác với transaction test | Dùng database riêng cho test, xóa fixture hoặc cleanup sau mỗi test |
| Cập nhật nhận 412 | ETag trong If-Match đã cũ hoặc không thuộc đúng resource URI | GET lại resource, lấy ETag mới và gửi đúng URI; nếu đang kiểm thử concurrency thì 412 là kết quả mong đợi |
| Validator không chạy | Bean name không gắn với event hoặc validator chưa được đăng ký | Dùng prefix event như `beforeCreateBookValidator`, hoặc đăng ký qua `configureValidatingRepositoryEventListener` |
| Query chạy trên H2 nhưng lỗi trên database production | Khác biệt dialect, constraint, collation hoặc native SQL | Chạy thêm test với database thật/Testcontainers và cấu hình `replace = NONE` |

## 7. Checklist trước khi hoàn tất

- [ ] Repository test bao phủ các truy vấn và mapping quan trọng.
- [ ] Test export chứng minh repository mong muốn có mặt và repository nội bộ không bị lộ.
- [ ] Test xác minh base path, collection path/rel, search endpoint và method exposure.
- [ ] HTTP test xác minh status, header, Content-Type/Accept và body.
- [ ] HAL test xác minh self/association/search/paging links cần thiết.
- [ ] Validation, security và lỗi đầu vào có test theo hợp đồng đã công bố.
- [ ] Nếu dùng ETag, đã kiểm tra cả ETag mới và ETag cũ.
- [ ] Có ít nhất một số end-to-end test cho luồng quan trọng nếu hệ thống cần kiểm tra container/network thực tế.
- [ ] Test độc lập, tự chuẩn bị dữ liệu và dọn dữ liệu đúng cách.

## 8. Tài liệu chính thức

- [Spring Data REST Reference](https://docs.spring.io/spring-data/rest/reference/) — tổng quan exporter, resources, representations, validation, security và customization.
- [Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html) — collection/item resources và HTTP method được hỗ trợ.
- [Customizing Spring Data REST](https://docs.spring.io/spring-data/rest/reference/customizing-sdr.html) — detection strategy và cấu hình exposure.
- [Paging and Sorting](https://docs.spring.io/spring-data/rest/reference/paging-and-sorting.html) — tham số page/size/sort và link điều hướng.
- [Validation](https://docs.spring.io/spring-data/rest/reference/validation.html) — đăng ký validator theo event.
- [ETags and other conditionals](https://docs.spring.io/spring-data/rest/reference/etags-and-other-conditionals.html) — ETag, If-Match, If-None-Match và status có điều kiện.
- [Testing Spring Boot applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html) — `@SpringBootTest`, web environment và test slices.
- [Spring Boot test modules](https://docs.spring.io/spring-boot/reference/testing/test-modules.html) — các module test theo chức năng.
- [MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html) — kiểm thử xử lý Spring MVC bằng mock request/response.
- [MockMvc vs end-to-end tests](https://docs.spring.io/spring-framework/reference/testing/mockmvc/vs-end-to-end-integration-tests.html) — giới hạn và khác biệt giữa mock MVC và server thật.
- [WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html) — kiểm thử với mock server hoặc live server.
- [Spring REST Docs: Hypermedia](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/hypermedia.html) — trích xuất và xác minh HAL links trong tài liệu API.
