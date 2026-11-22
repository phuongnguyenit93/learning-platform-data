# Schema validation trong CI với Spring for GraphQL

Schema GraphQL là hợp đồng giữa server và các client. Một thay đổi có thể làm ứng dụng vẫn compile nhưng khiến operation của mobile app, web app hoặc service khác không còn hợp lệ. Vì vậy, CI cần kiểm tra schema ở nhiều lớp: SDL có hợp lệ không, Spring có dựng được executable schema không, các operation đang dùng có còn validate được không và thay đổi có tương thích với schema đã phát hành không.

Với Spring for GraphQL, kiểm tra lúc ứng dụng khởi động là một lớp quan trọng nhưng chưa đủ. Ứng dụng có thể khởi động thành công trong khi một client operation vẫn gọi field đã bị xóa hoặc truyền argument sai kiểu. Một pipeline tốt kết hợp build/test của Spring, kiểm tra operation documents và schema compatibility check trước khi merge hoặc publish.

## Bốn lớp kiểm tra nên có trong CI

| Lớp kiểm tra | Câu hỏi cần trả lời | Công cụ hoặc cách làm |
| --- | --- | --- |
| SDL/schema validation | Schema có đúng cú pháp, type reference và quy tắc GraphQL không? | GraphQL parser/validator, GraphQL Inspector, Spring GraphQL schema initialization. |
| Runtime wiring validation | Spring có tạo được `GraphQlSource`, scalar, controller mapping và runtime wiring không? | Spring Boot context test, `@GraphQlTest`, `@SpringBootTest`. |
| Operation validation | Query/mutation/subscription documents của client có hợp lệ với schema mới không? | GraphQL Inspector `validate`, GraphQL Code Generator hoặc persisted operation checks. |
| Schema compatibility | Thay đổi có xóa hoặc siết contract mà client hiện tại đang dùng không? | GraphQL Inspector `diff`, Apollo GraphOS schema checks hoặc schema registry tương đương. |

Không công cụ đơn lẻ nào thay thế cả bốn lớp. Ví dụ, SDL parser không biết operation của client; operation validation không chứng minh resolver hoạt động đúng; schema diff không kiểm tra database hoặc authorization runtime.

## 1. Kiểm tra SDL và GraphQL type system

Trước khi dựng ứng dụng, kiểm tra các file `.graphqls`/`.graphql` để phát hiện lỗi cấu trúc:

- Cú pháp SDL sai hoặc khai báo trùng type, field, argument, enum value.
- Field tham chiếu tới type không tồn tại.
- Input object dùng output-only type hoặc output field dùng input-only type.
- Query/Mutation/Subscription root type không hợp lệ.
- Interface implementation thiếu field hoặc không tương thích kiểu.
- Union chứa member không phải object type.
- Default value không phù hợp kiểu khai báo.
- Directive được áp dụng sai vị trí hoặc sai argument theo định nghĩa.

Ví dụ schema lỗi vì field tham chiếu type chưa khai báo:

```graphql
type Query {
  book(id: ID!): Book
}

type Book {
  id: ID!
  author: AuthorProfile!
}
```

Nếu `AuthorProfile` chưa được khai báo trong toàn bộ schema, schema validation sẽ thất bại. Kiểm tra này nên chạy ngay sau khi SDL thay đổi để lỗi được phát hiện trước khi deploy.

### Spring for GraphQL dựng executable schema

Spring Boot nạp các schema resources và tạo `GraphQlSource` lúc khởi tạo application context. Quá trình này kiểm tra schema khi ghép các file SDL và áp dụng runtime wiring. Lỗi như type không tồn tại, scalar không được cấu hình hoặc runtime wiring không hợp lệ thường làm context khởi động thất bại.

Với Spring Boot, schema mặc định thường được tìm dưới `classpath:graphql/**/`. Có thể cấu hình vị trí khác bằng `spring.graphql.schema.locations`. Nếu schema được chia thành nhiều file theo domain, CI phải kiểm tra toàn bộ các file được ứng dụng nạp cùng nhau; kiểm tra từng file riêng lẻ có thể báo thiếu type được khai báo trong file khác hoặc bỏ qua xung đột khi ghép schema.

Kiểm tra context bằng một test khởi động ứng dụng:

```java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class GraphQlSchemaStartupTests {

    @Test
    void applicationContextBuildsGraphQlSchema() {
        // Nếu context khởi tạo thành công, schema và runtime wiring đã được dựng.
    }
}
```

Test này xác minh schema resources và cấu hình runtime của ứng dụng được nạp. Nó không thay thế operation validation, và có thể cần test fixture hoặc Testcontainers nếu application context phụ thuộc database/service bên ngoài.

### Kiểm tra GraphQL runtime qua `GraphQlTester`

Để xác minh schema thực sự nhận operation, có thể gửi một request nhỏ qua `ExecutionGraphQlServiceTester`:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.graphql.ExecutionGraphQlService;
import org.springframework.graphql.test.tester.ExecutionGraphQlServiceTester;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class GraphQlRuntimeSchemaTests {

    @Autowired
    ExecutionGraphQlService graphQlService;

    @Test
    void rootQueryTypeIsAvailable() {
        var tester = ExecutionGraphQlServiceTester.create(graphQlService);

        tester.document("{ __typename }")
                .execute()
                .path("__typename")
                .entity(String.class)
                .satisfies(typeName -> assertThat(typeName).isEqualTo("Query"));
    }
}
```

`__typename` là meta field của GraphQL, nên test trên xác minh root query có thể được thực thi. Nên bổ sung test operation quan trọng cho các query/mutation thực tế; test `__typename` một mình không xác minh field mapping, authorization hoặc service behavior.

Với test slice, `@GraphQlTest` tải phần GraphQL cần thiết và các controller được chọn. Với test tích hợp đầy đủ, `@SpringBootTest` kiểm tra cả cấu hình application context. Chọn phạm vi phù hợp, tránh để mọi test schema phải khởi động các dependency ngoài không cần thiết.

## 2. Validate operation documents của client

SDL hợp lệ không đảm bảo các operation cũ còn chạy. Ví dụ schema có thể xóa `Book.subtitle`, đổi argument `id` thành `bookId` hoặc đổi một enum value. Server vẫn dựng được schema mới, nhưng operation lưu trong web/mobile client có thể không còn validate.

Đặt operation documents trong repository hoặc lấy từ persisted operation registry. Ví dụ:

```graphql
# src/test/graphql/book-detail.graphql
query BookDetail($id: ID!) {
  book(id: $id) {
    id
    title
    subtitle
  }
}
```

Validate toàn bộ documents với schema candidate trước khi merge. GraphQL Inspector CLI cung cấp lệnh `validate`:

```bash
npx graphql-inspector validate 'src/**/*.graphql' schema/current.graphql
```

Lệnh này kiểm tra operation documents có hợp lệ với schema được chỉ định. Trong dự án có nhiều schema resources, `schema/current.graphql` cần là schema snapshot đã ghép từ đúng tập SDL mà Spring Boot sử dụng. Không validate operation với một file schema mẫu thiếu type hoặc field thật.

Operation validation bắt được các lỗi như:

- Client gọi field hoặc type đã bị xóa.
- Client truyền argument không còn tồn tại hoặc sai kiểu.
- Variable type không tương thích với argument.
- Query thiếu selection set cho object field hoặc có selection set trên scalar.
- Enum literal không còn được schema khai báo.
- Fragment tham chiếu type condition không hợp lệ.

Operation validation chỉ kiểm tra document và schema. Nó không xác minh giá trị runtime của variable, dữ liệu tồn tại trong database, quyền truy cập hoặc resolver có trả đúng kết quả hay không; các phần đó cần integration/contract tests riêng.

### Nguồn operation documents

CI nên kiểm tra operation từ các nguồn mà tổ chức thực sự quản lý:

1. Documents trong repository của frontend hoặc backend consumer.
2. Persisted queries được publish cùng ứng dụng.
3. Operation registry của nền tảng GraphQL nếu có.
4. Bộ operation contract test được lưu trong repository server.

Nếu client nằm ở repository khác, có thể chạy schema checks từ pipeline client hoặc tải operation artifact đã publish. Không nên chỉ validate một thư mục test nhỏ rồi kết luận mọi client đang dùng đều tương thích.

Với operation registry, cần phân biệt operation đang hoạt động và operation cũ không còn traffic. Dùng lịch sử usage trong khoảng thời gian phù hợp để quyết định deprecate/remove; operation không xuất hiện trong repository server không có nghĩa là không có client bên ngoài đang gọi.

## 3. So sánh schema candidate với schema baseline

Schema diff so sánh schema trong pull request với một baseline đã được chấp nhận, thường là schema trên nhánh chính hoặc schema đã publish trong registry. Mục tiêu là phát hiện thay đổi có thể phá vỡ client trước khi release.

GraphQL Inspector có lệnh `diff`:

```bash
npx graphql-inspector diff schema/baseline.graphql schema/current.graphql
```

Trong lệnh trên, file thứ nhất là schema baseline, file thứ hai là schema candidate của pull request. Đặt diff vào CI để pipeline thất bại khi có breaking change theo rule/exit code của phiên bản CLI được pin trong dự án. Không dùng schema candidate làm cả hai đầu vào vì kết quả sẽ không phát hiện thay đổi.

### Ví dụ thay đổi cần chú ý

| Thay đổi schema | Rủi ro với client |
| --- | --- |
| Xóa field/type đang được dùng | Operation không còn validate. |
| Đổi tên field hoặc argument | Client cũ tham chiếu tên cũ sẽ lỗi. |
| Thêm argument Non-Null không có default vào field hiện có | Operation cũ không truyền argument sẽ không hợp lệ. |
| Input field nullable thành Non-Null | Client có thể bỏ qua hoặc gửi null; operation/variables có thể thất bại. |
| Xóa enum value dùng trong input | Client gửi enum value cũ không còn hợp lệ. |
| Output Non-Null thành nullable | Client có thể nhận null dù generated type cũ kỳ vọng có giá trị. |
| Output nullable thành Non-Null | Thường an toàn với client nếu resolver bảo đảm; cần kiểm tra null propagation và dữ liệu. |
| Thêm field output nullable | Thường không ảnh hưởng operation hiện tại. |
| Thêm input field nullable hoặc có default | Thường không bắt client cũ thay đổi request. |

Phân loại compatibility phụ thuộc vị trí input/output và list/item nullability. Không chỉ nhìn thông báo `type changed`: cần kiểm tra client operation và dữ liệu runtime. Một số công cụ có thể phân loại thay đổi output nullable thành Non-Null là thay đổi type hoặc cảnh báo; con người vẫn phải xác minh guarantee của resolver.

### Breaking, dangerous và non-breaking

- **Breaking:** operation cũ không còn validate hoặc giá trị mà client dựa vào không còn được bảo đảm.
- **Dangerous:** schema vẫn hợp lệ nhưng có thể làm client thay đổi hành vi, ví dụ thêm enum value vào output mà client generated code xử lý exhaustive.
- **Non-breaking:** mở rộng schema theo cách client cũ có thể tiếp tục hoạt động, ví dụ thêm field output nullable.

Thêm enum value thường là mở rộng với input vì server chấp nhận thêm giá trị. Với output, client có thể dùng exhaustive switch hoặc generated enum không có nhánh cho giá trị mới; do đó phải đánh giá consumer behavior thay vì mặc định mọi enum addition đều an toàn.

Deprecate field không xóa field và thường không làm operation cũ thất bại. Tuy nhiên, deprecation cần có thời gian migration, usage tracking và bước xóa riêng.

## 4. Dùng schema registry và operation checks

Với hệ thống nhiều client hoặc nhiều subgraph, một schema registry giúp lưu schema đã publish, theo dõi operation usage và chạy compatibility checks so với variant đang triển khai.

Apollo GraphOS hỗ trợ schema checks cho schema candidate trong pull request. Một flow phổ biến:

1. Publish hoặc cung cấp schema candidate từ branch/CI.
2. So sánh candidate với schema đã publish của graph variant đích.
3. Kiểm tra operation đã quan sát để xác định client nào có thể bị ảnh hưởng.
4. Đưa kết quả check vào pull request để reviewer quyết định merge.

Ví dụ dùng Apollo Rover CLI (cần graph ref và `APOLLO_KEY` được cấu hình trong secret của CI):

```bash
rover graph check my-graph@current --schema ./schema/current.graphql
```

`my-graph@current` là ví dụ graph reference; thay bằng graph và variant thực tế. Lệnh check sử dụng schema candidate để chạy schema/operation checks theo cấu hình GraphOS. Cần pin Rover version và đọc kết quả check; không coi việc upload schema hoặc publish schema là tương đương với check compatibility.

Với Federation, schema cần được kiểm tra ở cả cấp subgraph và supergraph composition. Một subgraph SDL có thể hợp lệ riêng nhưng không compose được với các subgraph khác do xung đột type, key, field ownership hoặc directive. Chạy subgraph check/composition check theo graph registry trước khi deploy gateway hoặc subgraph.

Schema registry hữu ích khi operation nằm ở nhiều repository hoặc client được phát hành độc lập. Nếu dự án nhỏ và mọi operation nằm cùng repository, GraphQL Inspector diff/validate cùng Spring integration tests có thể đã đủ; không cần thêm registry chỉ để có thêm một công cụ.

## 5. Tạo schema artifact nhất quán cho CI

Schema candidate được dùng trong diff và operation validation phải phản ánh đúng schema mà ứng dụng sẽ chạy. Đây là điểm dễ sai khi Spring Boot nạp nhiều file SDL, custom scalar hoặc schema được mở rộng bằng runtime wiring.

Ví dụ source layout:

```text
src/main/resources/graphql/
├── common.graphqls
├── catalog.graphqls
├── orders.graphqls
└── customers.graphqls
```

Đảm bảo pipeline kiểm tra cùng tập resources, cùng custom directives và cùng cách ghép schema. Có thể:

- Duy trì một SDL artifact đã compose làm đầu vào cho schema diff và operation validation.
- Dùng schema export task của dự án để sinh candidate artifact từ chính schema resources.
- Dùng schema registry/composition tooling để build candidate từ các subgraph SDL.

Không tạo một `schema/current.graphql` thủ công rồi quên cập nhật khi thêm file `.graphqls` mới. Khi đó CI có thể xanh dù runtime schema đã thay đổi. Nên kiểm tra artifact được sinh từ cùng nguồn và lưu nó như build artifact để reviewer có thể tải về.

Custom scalar và directive wiring cần được kiểm tra ở runtime. SDL validator có thể biết scalar name đã được khai báo nhưng không chứng minh parser/serializer Java xử lý đúng. Spring context test và GraphQlTester integration test bổ sung lớp xác minh này.

## 6. Ví dụ pipeline GitHub Actions

Ví dụ dưới đây giả định repository có:

- Gradle wrapper để chạy Spring tests.
- `schema/current.graphql` là SDL candidate đã compose từ schema resources.
- `schema/baseline.graphql` được lấy từ nhánh base.
- Operation documents trong `src/test/graphql/`.
- `@graphql-inspector/cli` được pin trong `package-lock.json`.

```yaml
name: GraphQL schema checks

on:
  pull_request:
  push:
    branches: [main]

jobs:
  schema-validation:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'

      - uses: gradle/actions/setup-gradle@v4

      - name: Run Spring tests and build
        run: ./gradlew clean check

      - uses: actions/setup-node@v4
        with:
          node-version: '22'
          cache: npm

      - name: Install schema tooling
        run: npm ci

      - name: Validate client operations
        run: npx graphql-inspector validate 'src/test/graphql/**/*.graphql' schema/current.graphql

      - name: Fetch base schema
        if: github.event_name == 'pull_request'
        env:
          BASE_REF: ${{ github.base_ref }}
        run: |
          git fetch origin "$BASE_REF" --depth=1
          git show "origin/$BASE_REF:schema/current.graphql" > schema/baseline.graphql

      - name: Check schema compatibility
        if: github.event_name == 'pull_request'
        run: npx graphql-inspector diff schema/baseline.graphql schema/current.graphql
```

Trong ví dụ, `npm ci` dùng package lock để cố định phiên bản CLI. Thêm `@graphql-inspector/cli` vào `devDependencies` và commit `package-lock.json`. Nếu repository dùng Maven, thay `./gradlew clean check` bằng `./mvnw verify`.

Với push trực tiếp lên `main`, có thể lưu schema đã publish như artifact hoặc lấy baseline từ tag/release gần nhất. Không lấy candidate làm baseline cho chính nó.

Nếu schema artifact được tạo trong Gradle, thêm bước export trước các lệnh `validate`/`diff` và đảm bảo `schema/current.graphql` đã tồn tại. Ví dụ trên cố ý tách bước export vì cách xuất SDL phụ thuộc cấu trúc schema resources và custom wiring của từng ứng dụng.

## 7. Ví dụ cấu hình GraphQL Inspector

Pin CLI trong `package.json` để mọi máy và CI dùng cùng phiên bản:

```json
{
  "private": true,
  "devDependencies": {
    "@graphql-inspector/cli": "<pinned-version>"
  }
}
```

Thay `<pinned-version>` bằng phiên bản đã được dự án kiểm thử và commit lockfile. Tránh dùng `npx` không pin version trong pipeline quan trọng vì rule hoặc exit behavior có thể thay đổi giữa các lần chạy.

Các lệnh thường dùng:

```bash
# Kiểm tra operation documents
npx graphql-inspector validate 'src/test/graphql/**/*.graphql' schema/current.graphql

# So sánh schema baseline và candidate
npx graphql-inspector diff schema/baseline.graphql schema/current.graphql
```

Đối với dự án có nhiều operation directory, truyền các glob phù hợp cho toàn bộ client documents thuộc phạm vi kiểm soát. Đối với dự án dùng GraphQL Config, có thể khai báo schema/documents trong cấu hình chung để editor, codegen và CI dùng cùng nguồn.

## 8. Đưa schema checks vào quy trình pull request

Một pull request thay đổi schema nên cung cấp đủ thông tin để reviewer đánh giá:

- SDL diff: field/type/argument/input/enum/directive nào được thêm, sửa hoặc xóa.
- Compatibility result: breaking/dangerous changes và operation bị ảnh hưởng.
- Runtime test result: `GraphQlSource` khởi tạo, scalar/wiring hoạt động và operation test quan trọng pass.
- Ownership: domain/client nào chịu ảnh hưởng và ai xác nhận migration.
- Rollout plan: thêm field mới, deprecate field cũ, theo dõi usage và thời điểm xóa.

CI nên chặn merge khi schema không hợp lệ, operation nội bộ không validate hoặc có breaking change chưa được chấp thuận. Dangerous change có thể yêu cầu review bổ sung thay vì tự động chặn trong mọi dự án.

Với thay đổi có chủ đích gây breaking, không nên tắt toàn bộ schema checks. Tạo quy trình exception có ghi lý do, client/operation bị ảnh hưởng, kế hoạch phát hành và người chấp thuận. Có thể dùng version/variant riêng hoặc phát hành theo giai đoạn nếu client không thể cập nhật đồng thời.

## 9. Lỗi thường gặp khi thiết lập CI

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Spring tests pass nhưng client lỗi sau deploy | Chỉ kiểm tra application startup, không validate operation documents. | Thêm operation validation cho documents và registry. |
| SDL diff báo không có thay đổi dù đã sửa schema | Baseline và candidate trỏ cùng artifact hoặc candidate chưa được export lại. | Kiểm tra hai đầu vào và thêm bước tạo schema artifact rõ ràng. |
| CLI báo thiếu type khi chạy trên một file | Schema thực tế được ghép từ nhiều `.graphqls` resources. | Validate/diff schema đã compose từ toàn bộ resources. |
| Operation validation pass nhưng runtime lỗi | Custom scalar, directive, controller mapping hoặc service wiring không được kiểm tra bởi static validation. | Thêm Spring context và GraphQlTester integration tests. |
| Schema diff không phát hiện client ngoài repository | Operation documents của client chưa được đưa vào CI hoặc registry. | Kết nối operation registry/consumer artifacts và theo dõi usage. |
| Thêm enum value gây lỗi client | Client generated code dùng exhaustive switch hoặc enum mapping nghiêm ngặt. | Xem enum output addition là dangerous và kiểm tra consumer. |
| CI không tìm thấy schema baseline | Base branch chưa được fetch hoặc path artifact khác giữa branch. | Fetch base ref và kiểm tra path/schema export step. |
| Kết quả check thay đổi không ổn định | CLI/tool version không được pin. | Pin dependency, lockfile, Rover version và cấu hình rules. |
| Subgraph hợp lệ nhưng gateway không compose | Chỉ kiểm tra subgraph SDL, không kiểm tra supergraph composition. | Thêm Federation composition/schema registry check. |
| Schema check pass nhưng resolver trả dữ liệu sai | Compatibility check không kiểm tra business behavior. | Bổ sung resolver, authorization và database integration tests. |

## 10. Checklist schema validation trong CI

- [ ] Tất cả schema resources được đưa vào cùng một schema candidate.
- [ ] SDL parse và GraphQL type-system validation pass.
- [ ] Spring application context tạo được `GraphQlSource` và runtime wiring.
- [ ] Custom scalar/directive và controller mappings quan trọng có integration test.
- [ ] Operation documents của các client được validate với schema candidate.
- [ ] Candidate được diff với baseline đúng từ base branch hoặc schema registry.
- [ ] Breaking/dangerous changes có owner và quyết định rõ ràng.
- [ ] Federation subgraph composition được kiểm tra nếu hệ thống dùng Federation.
- [ ] CLI, schema tooling và dependency versions được pin.
- [ ] Schema artifact và kết quả check được lưu trong CI để reviewer truy xuất.

## Ghi nhớ

Schema validation trong CI cần nhiều lớp. Spring Boot context test xác nhận schema và runtime wiring dựng được; GraphQL Inspector `validate` xác nhận operation documents còn hợp lệ; `diff` hoặc schema registry checks phát hiện thay đổi contract có thể ảnh hưởng client. Với nhiều client hoặc Federation, cần đưa persisted operations và composition checks vào pipeline.

Giữ schema candidate nhất quán với toàn bộ `.graphqls` resources mà ứng dụng thực sự nạp. Pin công cụ, so sánh với baseline đúng, kiểm tra runtime bằng GraphQlTester và yêu cầu review cho breaking/dangerous changes. CI xanh chỉ xác nhận các hợp đồng đã được đưa vào kiểm tra; operation bên ngoài chưa đăng ký và behavior nghiệp vụ vẫn cần được quản lý bằng registry, monitoring và integration tests.

## Tài liệu tham khảo

- [Spring for GraphQL — Testing](https://docs.spring.io/spring-graphql/reference/testing.html)
- [Spring Boot — GraphQL](https://docs.spring.io/spring-boot/reference/web/spring-graphql.html)
- [GraphQL Inspector — CLI](https://the-guild.dev/graphql/inspector/docs/essentials/cli)
- [Apollo Rover — `graph check`](https://www.apollographql.com/docs/rover/commands/graphs)
- [Apollo GraphOS — Schema Checks](https://www.apollographql.com/docs/graphos/platform/schema-management/checks)
- [GraphQL Specification — Validation](https://spec.graphql.org/September2026/#sec-Validation)
