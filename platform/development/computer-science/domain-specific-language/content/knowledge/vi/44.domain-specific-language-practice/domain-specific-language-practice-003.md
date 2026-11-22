# Xác định ví dụ chuẩn

Trong một dự án thực hành DSL (Domain-Specific Language), ví dụ là cầu nối giữa thiết kế ngôn ngữ và cách người dùng thực sự viết, đọc, kiểm tra và triển khai chương trình. Một bộ ví dụ tốt cho thấy DSL biểu đạt được những bài toán nào, cú pháp được dùng ra sao, kết quả mong đợi là gì và những giới hạn nào cần lưu ý. **Xác định ví dụ chuẩn** là quá trình lựa chọn, thiết kế, mô tả và quản lý một tập ví dụ đại diện để làm tài liệu tham khảo, kiểm thử và tiêu chí thống nhất cho dự án.

Ví dụ chuẩn không chỉ là vài đoạn code minh họa. Chúng cần đại diện cho use case thật, thể hiện những tính năng cốt lõi, đủ nhỏ để dễ hiểu, có kết quả có thể xác minh và được duy trì cùng version của DSL. Trong dự án thực hành, ví dụ chuẩn còn giúp nhóm thống nhất phạm vi, phân chia module, kiểm tra compiler/runtime và đánh giá xem thiết kế ngôn ngữ có giải quyết được vấn đề ban đầu hay không.

## 1. Ví dụ chuẩn là gì?

Ví dụ chuẩn (canonical/reference example) là ví dụ được chọn làm mẫu chính thức cho một khái niệm, tính năng hoặc luồng sử dụng của DSL. Nó thể hiện cách viết được khuyến nghị và hành vi mà người dùng có thể kỳ vọng.

Một ví dụ chuẩn thường có:

- Mục tiêu hoặc use case rõ ràng.
- Source DSL hợp lệ và có thể chạy hoặc phân tích.
- Giải thích cú pháp và domain concepts.
- Kết quả mong đợi hoặc output có thể xác minh.
- Phiên bản DSL/toolchain được hỗ trợ.
- Dependencies và cách chạy.
- Test tự động để phát hiện ví dụ lỗi thời.
- Owner hoặc nơi quản lý khi cần cập nhật.

Ví dụ đơn giản:

~~~text
entity Customer {
    id: CustomerId
    name: String
    email: EmailAddress
}

rule validCustomer {
    require notBlank(name)
    require validEmail(email)
}
~~~

Ví dụ này có thể là mẫu cho entity declaration và validation rule. Nó nên đi kèm giải thích entity, field types, rule scope và cách validator báo lỗi khi dữ liệu không hợp lệ.

### 1.1. Ví dụ chuẩn khác snippet tùy ý

Snippet có thể minh họa một dòng syntax nhưng không đủ context để chạy. Ví dụ chuẩn cần đủ ngữ cảnh để người đọc hiểu và, nếu mục tiêu yêu cầu, có thể copy vào project để chạy.

### 1.2. Ví dụ chuẩn khác test fixture thuần túy

Test fixture có thể cố tình chứa cú pháp bất thường hoặc dữ liệu nhỏ để kiểm tra edge case. Ví dụ chuẩn hướng tới người dùng và thể hiện cách dùng được khuyến nghị. Một fixture có thể trở thành ví dụ chuẩn nếu nó có context, explanation và expected behavior phù hợp.

### 1.3. Ví dụ chuẩn không nhất thiết là ví dụ phức tạp nhất

Một ví dụ nhỏ, rõ và đại diện thường hữu ích hơn một project lớn chứa quá nhiều tính năng. Độ phức tạp nên tăng theo mục tiêu học tập.

## 2. Vì sao cần xác định ví dụ chuẩn?

Một dự án DSL có thể có nhiều người thiết kế grammar, compiler, runtime và tài liệu. Nếu không có bộ ví dụ thống nhất, mỗi người có thể hiểu syntax hoặc semantics khác nhau.

Ví dụ chuẩn giúp:

- Làm rõ DSL được thiết kế để giải quyết bài toán nào.
- Thống nhất cú pháp và phong cách viết.
- Làm căn cứ cho parser, validator và generator tests.
- Hướng dẫn người mới học từ ví dụ đơn giản đến hoàn chỉnh.
- Phát hiện thiếu sót của grammar và semantic model.
- So sánh hành vi trước/sau khi thay đổi compiler.
- Đánh giá khả năng đọc và bảo trì của DSL.
- Tạo dữ liệu mẫu cho IDE, documentation và workshop.
- Hạn chế ví dụ trong tài liệu bị lỗi thời.
- Đưa ra tiêu chí hoàn thành cho dự án thực hành.

### 2.1. Ví dụ là một phần của thiết kế ngôn ngữ

Khi viết ví dụ, nhóm sẽ nhận ra cú pháp có tự nhiên không, tên gọi có rõ không, cấu trúc có lặp lại quá nhiều không và người dùng có thể biểu đạt use case thật không. Ví dụ có thể phát hiện vấn đề thiết kế trước khi grammar được triển khai đầy đủ.

### 2.2. Ví dụ là hợp đồng hành vi

Nếu một ví dụ được đánh dấu là canonical và đưa vào test suite, thay đổi làm ví dụ không còn parse hoặc tạo output khác có thể là breaking change hoặc ít nhất cần review.

### 2.3. Ví dụ tạo ngôn ngữ chung trong nhóm

Product owner có thể dùng ví dụ để xác nhận yêu cầu; compiler developer dùng để kiểm tra parser; người viết tài liệu dùng để minh họa; người vận hành dùng để kiểm tra deployment. Cùng một artifact giúp giảm diễn giải khác nhau.

## 3. Phân loại ví dụ

Không nên dùng một ví dụ duy nhất cho mọi mục đích. Có thể xây dựng catalog theo loại.

| Loại ví dụ | Mục tiêu | Quy mô |
|---|---|---|
| Minimal syntax example | Giới thiệu một construct | Vài dòng |
| Concept example | Giải thích một khái niệm domain | Nhỏ |
| Feature example | Minh họa một tính năng DSL | Nhỏ đến vừa |
| End-to-end example | Thể hiện luồng từ source đến output | Vừa |
| Project example | Cho thấy cấu trúc repository/module | Vừa đến lớn |
| Error example | Minh họa diagnostic và cách sửa | Nhỏ |
| Integration example | Kết nối DSL với API/database/service | Vừa |
| Migration example | Chuyển source giữa phiên bản | Nhỏ đến vừa |
| Performance example | Minh họa workload và đo đạc | Có thể lớn |
| Security example | Minh họa policy và quyền | Nhỏ đến vừa |

### 3.1. Minimal examples

Minimal example chỉ chứa cấu trúc cần thiết để giải thích một syntax. Nó phù hợp cho reference page và unit test.

### 3.2. Conceptual examples

Concept example giải thích ý nghĩa domain, ví dụ entity, workflow state hoặc policy. Có thể dùng pseudocode nếu chưa cần chạy.

### 3.3. Feature examples

Feature example tập trung một capability như import, generic, event subscription hoặc query pagination. Nó cần thể hiện input và behavior liên quan.

### 3.4. End-to-end examples

End-to-end example kết nối nhiều thành phần: source DSL, parser, semantic validation, generated artifact và runtime behavior. Đây là mẫu quan trọng cho dự án thực hành.

### 3.5. Negative examples

Negative example cố tình sai để giải thích diagnostic. Cần ghi rõ đây là input không hợp lệ và đưa ra expected error hoặc cách sửa.

## 4. Tiêu chí lựa chọn ví dụ chuẩn

Một ví dụ được chọn nên đáp ứng các tiêu chí phù hợp với mục tiêu của nó.

### 4.1. Tính đại diện

Ví dụ cần phản ánh use case thực tế hoặc khái niệm cốt lõi. Tránh chọn ví dụ chỉ đẹp về cú pháp nhưng không liên quan đến domain của DSL.

### 4.2. Tính tối giản

Loại bỏ phần không phục vụ mục tiêu. Nếu muốn dạy import, không cần đưa thêm concurrency, retry và code generation trừ khi chúng liên quan trực tiếp.

### 4.3. Tính đầy đủ

Ví dụ cần đủ context để hiểu. Nếu dùng một type, hãy khai báo hoặc liên kết rõ nơi type đó được định nghĩa. Nếu cần dependency, nêu rõ cách lấy.

### 4.4. Tính chạy được

Với ví dụ executable, phải có lệnh chạy, input và expected output. Không nên công bố ví dụ như thể chạy được nếu nó chỉ là pseudocode.

### 4.5. Tính xác định

Kết quả nên ổn định giữa các lần chạy. Tránh phụ thuộc timestamp, random values, external network hoặc dữ liệu production nếu không có kiểm soát.

### 4.6. Tính dễ đọc

Tên module, variable và domain terms nên có nghĩa. Ví dụ cần format nhất quán và tránh viết tắt không giải thích.

### 4.7. Tính mở rộng

Ví dụ có thể được mở rộng thành bài thực hành hoặc project lớn hơn. Nên chọn domain cho phép thêm tính năng mà không phải viết lại toàn bộ.

### 4.8. Tính an toàn

Không dùng secret thật, dữ liệu cá nhân, endpoint production hoặc thao tác phá hủy trong ví dụ. Những ví dụ có side effects cần dùng sandbox hoặc mock.

### 4.9. Khả năng kiểm thử

Nên có cách kiểm tra ví dụ tự động: parser test, semantic validation, golden output hoặc integration test. Nếu không thể tự động hóa, nêu rõ bước xác minh thủ công.

## 5. Chọn domain xuyên suốt cho dự án thực hành

Một dự án thực hành nên chọn một domain đủ quen thuộc để người học hiểu, nhưng đủ phong phú để thể hiện các tính năng DSL.

Một số domain phù hợp:

| Domain | Khái niệm có thể biểu đạt |
|---|---|
| Order management | Entity, validation, workflow, event, query |
| Booking | Resource, time, conflict, state transition |
| Inventory | Quantity, reservation, event, policy |
| Billing | Money, invoice, tax, payment |
| Workflow approval | Role, transition, timeout, audit |
| Configuration | Profile, environment, override, schema |
| API description | Resource, operation, schema, security |

### 5.1. Chọn domain có ranh giới rõ

Tránh domain quá rộng như quản lý doanh nghiệp. Một domain cụ thể như xử lý đơn hàng cho phép xác định entity, workflow và kết quả rõ hơn.

### 5.2. Tránh ví dụ quá phụ thuộc tổ chức

Nếu ví dụ cần dữ liệu nội bộ hoặc thuật ngữ riêng, người học bên ngoài khó hiểu. Dùng domain phổ biến và dữ liệu giả lập.

### 5.3. Chọn domain có thể mở rộng theo chương

Ví dụ ban đầu có thể là khai báo entity, sau đó thêm validation, query, workflow, event, API và deployment. Một domain xuyên suốt giúp người học thấy các phần DSL liên kết thế nào.

### 5.4. Không ép mọi tính năng vào một domain

Một số tính năng như grammar composition hoặc metamodel reuse có thể cần ví dụ riêng. Bộ ví dụ chuẩn nên cân bằng giữa câu chuyện xuyên suốt và ví dụ tập trung.

## 6. Xây dựng ma trận bao phủ tính năng

Trước khi viết hàng loạt ví dụ, lập ma trận tính năng để biết mỗi construct có mẫu đại diện nào.

Ví dụ:

| Tính năng DSL | Ví dụ chuẩn | Kiểm tra |
|---|---|---|
| Entity declaration | customer-model.dsl | Parse và AST |
| Type reference | order-types.dsl | Linking |
| Validation rule | customer-validation.dsl | Semantic diagnostics |
| Query/filter | open-orders.dsl | Query result |
| Sorting/pagination | order-pages.dsl | Stable page results |
| Workflow | fulfill-order.dsl | State transitions |
| Event subscription | payment-events.dsl | Correlation/resume |
| API operation | order-api.dsl | Contract generation |
| Environment profile | staging-profile.dsl | Effective config |
| Code generation | generated-order-app | Target compilation |

### 6.1. Coverage theo construct

Mỗi parser rule hoặc semantic feature quan trọng nên có ít nhất một fixture hợp lệ. Các trường hợp có nhiều nhánh cần nhiều ví dụ hơn.

### 6.2. Coverage theo user journey

Ngoài từng construct, cần ít nhất một luồng từ đầu đến cuối để chứng minh các thành phần hoạt động cùng nhau.

### 6.3. Coverage theo lỗi

Mỗi nhóm validation quan trọng nên có ví dụ lỗi và expected diagnostic. Người dùng học được cả cách viết đúng và cách nhận biết sai.

### 6.4. Coverage không phải số lượng ví dụ

Có nhiều file không đồng nghĩa bao phủ tốt. Một ví dụ trùng lặp không thêm giá trị. Nên đo theo tính năng, use case và hành vi được kiểm tra.

## 7. Cấu trúc của một ví dụ chuẩn

Một ví dụ trong catalog có thể dùng cấu trúc:

1. Title và mục tiêu.
2. Level hoặc prerequisite.
3. Use case.
4. Source DSL.
5. Dependencies và file layout.
6. Cách chạy.
7. Expected output hoặc behavior.
8. Giải thích các phần chính.
9. Các biến thể hoặc edge cases.
10. Liên kết đến feature/reference liên quan.
11. Version và owner.

### 7.1. Metadata

Có thể lưu metadata trong manifest:

~~~yaml
id: workflow-order-approval
title: Order approval workflow
level: intermediate
features:
  - workflow
  - event
  - timeout
files:
  - workflow/order-approval.dsl
expected:
  - workflow-completes-after-approval
dslVersion: "2.x"
~~~

Metadata giúp documentation site và test harness tìm ví dụ theo feature.

### 7.2. Mục tiêu học tập

Nêu rõ người đọc sẽ học được gì. Ví dụ “Sau ví dụ này, người đọc có thể khai báo workflow, chờ approval event và xử lý timeout.”

### 7.3. Prerequisites

Ghi compiler/runtime version, module cần import và kiến thức cần có. Tránh bắt người đọc đoán môi trường.

### 7.4. Expected result

Nếu ví dụ sinh file, liệt kê file hoặc digest/summary mong đợi. Nếu thực thi workflow, mô tả state transitions và event sequence.

### 7.5. Cleanup

Với ví dụ tạo resource hoặc chạy service, nêu cách dọn dữ liệu test và dừng process. Không để ví dụ làm thay đổi môi trường ngoài ý muốn.

## 8. Ví dụ chuẩn cho cú pháp cơ bản

Một bộ DSL cần bắt đầu từ construct cơ bản: module, declaration, type và literal.

Ví dụ:

~~~text
module shop.catalog

type ProductId = Identifier

entity Product {
    id: ProductId
    name: String
    price: Money
    active: Boolean = true
}
~~~

Ví dụ này có thể làm chuẩn cho:

- Module declaration.
- Type alias.
- Entity declaration.
- Field declaration.
- Primitive/domain types.
- Default values.

### 8.1. Giữ ví dụ tập trung

Không nên thêm import, inheritance hoặc validation vào ví dụ đầu tiên nếu mục tiêu là giới thiệu entity.

### 8.2. Giải thích default

Nếu field có default, giải thích default được áp dụng lúc parse, model construction hay runtime. Semantics này ảnh hưởng người dùng và cần rõ.

### 8.3. Expected AST

Có thể kèm sơ đồ AST rút gọn để giải thích parser tạo model nào. Không cần in toàn bộ internal node metadata nếu không phục vụ người đọc.

## 9. Ví dụ chuẩn cho validation và diagnostics

Một ví dụ validation nên có cả source hợp lệ và source sai.

Source:

~~~text
entity Customer {
    email: EmailAddress
    age: Integer
}

rule validCustomer {
    require age >= 0
    require validEmail(email)
}
~~~

Input không hợp lệ:

~~~text
Customer {
    email = "not-an-email"
    age = -3
}
~~~

Expected diagnostics:

~~~text
ERROR INVALID_EMAIL at email
ERROR NEGATIVE_AGE at age
~~~

### 9.1. Diagnostic code

Nếu compiler có stable error code, dùng code đó trong ví dụ. Message có thể thay đổi theo phiên bản hoặc locale.

### 9.2. Source location

Nên chỉ rõ vị trí lỗi và vùng highlight mong đợi. Điều này hữu ích cho editor integration.

### 9.3. Fix suggestion

Có thể đưa source đã sửa và giải thích vì sao hợp lệ. Không nên đưa quick fix nếu sửa tự động có thể thay đổi ý nghĩa nghiệp vụ.

## 10. Ví dụ chuẩn cho query DSL

Query example cần có dataset nhỏ và expected rows để người đọc kiểm tra được kết quả.

Source:

~~~text
query openOrders {
    from Order
    where status in [PENDING, PAID]
    orderBy createdAt descending, id ascending
    limit 20
}
~~~

Dataset fixture:

| id | status | createdAt |
|---|---|---|
| o-101 | PENDING | 2026-01-10 |
| o-102 | PAID | 2026-01-12 |
| o-103 | SHIPPED | 2026-01-13 |
| o-104 | PENDING | 2026-01-12 |

Expected result nên chỉ chứa o-102, o-104 và o-101 theo ordering đã khai báo, với tie-breaker khi timestamp bằng nhau.

### 10.1. Dữ liệu nhỏ và có chủ đích

Dataset nên đủ nhỏ để người đọc tính kết quả bằng tay. Nếu có null, duplicate hoặc boundary, ghi rõ mục tiêu của từng record.

### 10.2. Expected result

Không chỉ ghi “trả về danh sách đơn hàng”. Hãy liệt kê thứ tự record, page metadata hoặc output JSON.

### 10.3. Deterministic query

Dùng ordering tổng khi pagination cần ổn định. Không dựa vào thứ tự database mặc định.

## 11. Ví dụ chuẩn cho workflow và event

Một workflow example nên thể hiện state, transition, event, timeout và kết quả cuối.

~~~text
workflow fulfillOrder(orderId: OrderId) {
    let order = loadOrder(orderId)
    requestPayment(order)

    wait for PaymentCaptured
        where event.orderId == orderId
        timeout 15m
        as payment

    reserveInventory(order, payment)
    markOrderReady(order)
}
~~~

### 11.1. Event fixtures

Cần có event payload mẫu và correlation ID để test workflow resume đúng instance.

### 11.2. State timeline

Có thể trình bày timeline:

~~~text
Created
  -> AwaitingPayment
  -> PaymentCaptured
  -> InventoryReserved
  -> Ready
~~~

### 11.3. Timeout branch

Nên có ví dụ riêng cho timeout hoặc payment declined. Nếu chỉ có happy path, người đọc không biết workflow xử lý lỗi thế nào.

### 11.4. Side effects

Nếu ví dụ gửi email, trừ tiền hoặc tạo shipment, dùng fake service hoặc sandbox. Nêu rõ lệnh chạy không tác động production.

## 12. Ví dụ chuẩn cho API và dữ liệu

API example nên có contract, request, response và lỗi.

~~~text
service OrderApi {
    operation createOrder {
        method POST
        path "/v1/orders"
        request CreateOrderRequest
        response 201 Order
        errors [400, 401, 409, 422]
    }
}
~~~

Request:

~~~json
{
  "customerId": "cus-10",
  "items": [
    {"productId": "prd-3", "quantity": 2}
  ]
}
~~~

Expected response:

~~~json
{
  "id": "ord-42",
  "status": "PENDING"
}
~~~

### 12.1. Contract generation

Nếu DSL sinh OpenAPI hoặc schema, example nên bao gồm artifact được sinh hoặc link đến fixture để kiểm tra.

### 12.2. Security

Dùng token giả và sandbox endpoint. Không đặt credential thật trong ví dụ hoặc screenshot.

### 12.3. Error response

Có ít nhất một ví dụ validation/authentication error để consumer biết format lỗi.

## 13. Ví dụ chuẩn cho profile và cấu hình

Ví dụ configuration DSL nên thể hiện base profile, override và effective configuration.

~~~text
config service {
    port = 8080
    logging.level = INFO
}

profile development {
    logging.level = DEBUG
}

profile production {
    logging.level = WARN
    database.url = env("DATABASE_URL", required = true)
}
~~~

### 13.1. Tách secret

Chỉ dùng secret reference hoặc placeholder. Không lưu password thật trong sample.

### 13.2. Effective configuration

Hiển thị kết quả sau merge để người đọc hiểu precedence. Redact mọi secret value.

### 13.3. Validation

Có thể đưa một profile sai để minh họa required parameter hoặc cross-field constraint.

## 14. Ví dụ chuẩn cho import và model reuse

Ví dụ reuse nên có ít nhất hai module để thấy rõ dependency.

~~~text
module common.money {
    type Money {
        amount: Decimal
        currency: CurrencyCode
    }
}
~~~

~~~text
module sales.order {
    import common.money.Money

    entity Order {
        total: Money
    }
}
~~~

### 14.1. File layout

Cho biết file nào chứa module common và file nào import nó.

### 14.2. Build order

Nếu compiler cần dependency resolution, nêu cách load hoặc build package.

### 14.3. Version compatibility

Nếu module common có version, ghi version mà example dùng. Không dùng dynamic version không xác định.

## 15. Ví dụ chuẩn cho code generation

Code generation example cần thể hiện mối liên hệ giữa DSL source và output.

~~~text
entity Customer {
    id: CustomerId
    name: String
}
~~~

Generated output có thể là class hoặc schema target. Ví dụ:

~~~java
public final class Customer {
    private CustomerId id;
    private String name;
}
~~~

### 15.1. Generated files

Nêu thư mục output, file được tạo và cách regenerate.

### 15.2. Không sửa output bằng tay

Nếu output là generated artifact, hướng dẫn không nên yêu cầu người học sửa file generated. Thay đổi phải nằm trong DSL hoặc generator template.

### 15.3. Deterministic output

Golden output nên ổn định, không chứa absolute path hoặc timestamp không cần thiết.

### 15.4. Compile/run

Nếu generator sinh code, chạy target compiler hoặc test để xác nhận output có thể dùng được.

## 16. Ví dụ chuẩn cho error handling và edge cases

Bộ ví dụ không nên chỉ chứa happy path. Cần thể hiện các ranh giới mà người dùng dễ hiểu sai.

Các trường hợp nên có:

- Empty document.
- Missing required field.
- Unknown identifier.
- Duplicate declaration.
- Ambiguous import.
- Type mismatch.
- Invalid enum value.
- Null handling.
- Invalid date/time format.
- Circular dependency.
- Unsupported feature.
- Resource limit exceeded.
- Permission denied.
- Runtime timeout.

### 16.1. Error example có mục tiêu

Mỗi negative example nên nói rõ invariant nào bị vi phạm và expected diagnostic nào cần xuất hiện.

### 16.2. Không dạy cách dùng sai như best practice

Gắn nhãn rõ “Invalid example” hoặc “Anti-pattern”. Không đặt code sai cạnh code chuẩn mà không giải thích.

### 16.3. Edge cases có thể là test-only

Không phải mọi edge case cần đưa lên tutorial. Một số có thể chỉ tồn tại trong test corpus và reference dành cho compiler authors.

## 17. Example catalog và cấu trúc thư mục

Một dự án có thể tổ chức ví dụ như sau:

~~~text
examples/
├── 00-getting-started/
│   ├── hello.dsl
│   └── README.md
├── 10-language-basics/
│   ├── declarations/
│   ├── expressions/
│   └── types/
├── 20-domain-model/
│   ├── customer/
│   └── order/
├── 30-query/
│   ├── filtering/
│   └── pagination/
├── 40-workflow/
│   ├── approval/
│   └── events/
├── 50-integration/
│   ├── api/
│   └── codegen/
├── 90-error-cases/
└── manifest.yml
~~~

### 17.1. Numbering

Prefix số có thể giúp sắp xếp learning path, nhưng không nên làm ID ổn định phụ thuộc thứ tự. Dùng slug hoặc manifest ID cho deep links.

### 17.2. Group by concept

Nhóm theo concept giúp người dùng tìm nhanh. Có thể thêm tag như beginner, intermediate, security, runtime hoặc migration.

### 17.3. Một ví dụ, nhiều cách trình bày

Một source file có thể được dùng trong docs, tests và workshop. Tránh copy nội dung thành nhiều bản độc lập.

### 17.4. Example manifest

Manifest có thể lưu title, feature tags, source paths, expected outputs, DSL version, required dependencies và test command.

## 18. Ví dụ chuẩn như executable documentation

Một ví dụ có thể được chạy tự động để xác nhận tài liệu không lỗi thời.

### 18.1. Test harness

Test harness có thể tìm tất cả example manifest, parse source và chạy expected checks.

### 18.2. Golden files

Generated output có thể so sánh với golden file. Khi output thay đổi có chủ đích, reviewer xem diff và cập nhật fixture.

### 18.3. Smoke tests

Project example có thể build/run trong CI với dependency giả lập. Tránh gọi dịch vụ ngoài không ổn định nếu không cần.

### 18.4. Version pinning

Ví dụ cần khóa compiler/runtime version hoặc chạy trong matrix version được hỗ trợ. Nếu dùng latest không kiểm soát, ví dụ có thể hỏng ngẫu nhiên.

### 18.5. Documentation build

CI có thể kiểm tra link, snippet references và metadata. Nếu docs embed source file, build cần xác nhận file tồn tại.

### 18.6. Expected output normalization

Chuẩn hóa line endings, path và timestamp trước khi so sánh. Không bỏ qua khác biệt có ý nghĩa như thứ tự record hoặc error code.

## 19. Đánh giá độ khó và learning path

Ví dụ chuẩn nên hỗ trợ người học tiến dần từ cơ bản đến nâng cao.

Một lộ trình có thể là:

1. Hello DSL: parse một file tối thiểu.
2. Declarations: tạo type và entity.
3. Expressions: dùng operator và function.
4. Validation: thêm constraints.
5. Modules: import và reuse model.
6. Query: filter, order và paginate.
7. Workflow: state, event và timeout.
8. API: khai báo operation và schema.
9. Code generation: tạo target artifact.
10. Deployment: profile, build và release.

### 19.1. Prerequisite graph

Một số ví dụ cần ví dụ trước. Có thể biểu diễn dependency trong manifest để portal gợi ý thứ tự.

### 19.2. Progressive complexity

Mỗi ví dụ chỉ nên thêm một vài khái niệm mới. Nếu tăng nhiều concept cùng lúc, người học khó biết phần nào gây lỗi.

### 19.3. Optional challenges

Có thể thêm bài tập mở rộng sau ví dụ chuẩn, nhưng phải phân biệt expected solution với challenge do người học tự làm.

### 19.4. Learning outcomes

Mỗi example page nên nêu người học có thể làm gì sau khi hoàn thành, không chỉ liệt kê cú pháp đã dùng.

## 20. Quản lý version của ví dụ

Ví dụ có thể gắn với DSL version hoặc release branch.

### 20.1. Versioned examples

Nếu syntax thay đổi giữa major versions, có thể lưu ví dụ riêng theo version hoặc migration branch. Người dùng cũ cần truy cập đúng tài liệu.

### 20.2. Compatibility matrix

Ghi compiler/runtime version tối thiểu và các version được kiểm thử.

### 20.3. Deprecation

Khi một ví dụ dùng cú pháp deprecated, cần thay bằng ví dụ mới và giữ bản cũ trong migration guide nếu còn cần.

### 20.4. Changelog

Thay đổi expected output hoặc behavior của canonical example nên có lý do và liên kết đến issue/PR.

### 20.5. Immutable release examples

Release docs nên trỏ đến example snapshot tương ứng với version đã phát hành. Không sửa nội dung cũ khiến người dùng không thể tái tạo tài liệu lịch sử.

## 21. Review và governance cho ví dụ chuẩn

Ví dụ chuẩn ảnh hưởng đến cách cộng đồng hiểu DSL, nên cần review có trách nhiệm.

### 21.1. Example owner

Mỗi nhóm ví dụ có thể có owner chịu trách nhiệm source, expected output và documentation.

### 21.2. Review criteria

Reviewer có thể xem xét tính đại diện, tính dễ đọc, behavior, security, version và test coverage.

### 21.3. Canonical status

Không phải mọi sample đều canonical. Có thể đánh dấu stable/reference, experimental, tutorial-only hoặc test-only.

### 21.4. Thay đổi canonical example

Nếu ví dụ canonical đổi behavior, cần review như thay đổi contract. Nếu chỉ format hoặc typo, quy trình có thể nhẹ hơn.

### 21.5. Community feedback

Người dùng có thể đề xuất thêm example dựa trên use case thực tế. Maintainer nên đánh giá xem use case đó có phổ biến và phù hợp với mục tiêu dự án không.

## 22. Security và an toàn trong ví dụ

Ví dụ thường được copy vào dự án thật, vì vậy cần an toàn ngay từ đầu.

Các nguyên tắc:

- Dùng domain giả và dữ liệu synthetic.
- Không chứa API key, password hoặc private key.
- Không trỏ tới production endpoint.
- Không thực hiện thao tác xóa hoặc thanh toán thật.
- Dùng mock service hoặc sandbox.
- Giới hạn quyền của sample credentials.
- Ghi rõ side effects và cleanup.
- Không yêu cầu tắt TLS hoặc authorization để ví dụ chạy.
- Không dùng dependency không rõ nguồn.
- Không chứa dữ liệu cá nhân thật trong fixture.

### 22.1. Secure defaults

Ví dụ cấu hình nên dùng giá trị an toàn mặc định. Nếu cần minh họa insecure configuration để giải thích rủi ro, phải gắn nhãn rõ và không trình bày như cấu hình được khuyến nghị.

### 22.2. Sandbox isolation

Interactive examples cần chạy trong sandbox có quota, network policy và dữ liệu tạm. Người dùng phải biết thao tác nào có thể tạo tài nguyên.

### 22.3. Cleanup

Nếu example tạo database, container hoặc cloud resource, cung cấp lệnh cleanup và thời hạn tự dọn nếu có.

## 23. Đo lường chất lượng bộ ví dụ

Có thể theo dõi một số chỉ số:

- Tỷ lệ canonical examples parse/build thành công.
- Số feature có ví dụ đại diện.
- Số example bị deprecated.
- Số lỗi tài liệu do snippet không còn chạy.
- Thời gian hoàn thành getting-started task.
- Tỷ lệ người học hoàn tất tutorial.
- Số issue được giải quyết bằng link tới example.
- Tỷ lệ example có test tự động.

### 23.1. Không tối ưu chỉ theo số lượng

Mục tiêu không phải có càng nhiều ví dụ càng tốt. Một bộ nhỏ nhưng có cấu trúc, coverage và expected behavior rõ thường hữu ích hơn một thư mục sample lớn không được duy trì.

### 23.2. Feedback định tính

Quan sát người mới dùng example có thể cho thấy chỗ khó hiểu mà metric không thể hiện. Ghi lại câu hỏi lặp lại và cải thiện hướng dẫn.

### 23.3. Maintenance cost

Ví dụ phụ thuộc nhiều service hoặc package có thể tốn công giữ hoạt động. Cần cân nhắc giá trị học tập so với chi phí bảo trì.

## 24. Những lỗi thường gặp khi chọn ví dụ

| Sai lầm | Hậu quả | Cách khắc phục |
|---|---|---|
| Chọn ví dụ không liên quan domain | Người học khó hiểu mục tiêu DSL | Dùng use case đại diện |
| Ví dụ quá lớn ngay từ đầu | Khó học và khó debug | Bắt đầu từ minimal examples |
| Chỉ có happy path | Người dùng không biết xử lý lỗi | Thêm negative/edge examples |
| Không có expected output | Không biết ví dụ chạy đúng hay chưa | Ghi kết quả có thể xác minh |
| Dùng dữ liệu hoặc secret thật | Rò rỉ thông tin và nguy cơ side effects | Synthetic data và sandbox |
| Copy cùng snippet nhiều nơi | Nội dung lệch theo thời gian | Một source dùng ở nhiều nơi |
| Không version hóa | Ví dụ cũ bị nhầm là syntax hiện tại | Gắn DSL/toolchain version |
| Không chạy test tự động | Snippet lỗi thời không được phát hiện | Executable documentation |
| Chỉ bao phủ grammar | Thiếu semantics/runtime behavior | Feature và end-to-end examples |
| Không có owner | Ví dụ hỏng nhưng không ai sửa | Gán ownership |
| Chọn quá nhiều edge cases làm tutorial | Learning path quá nặng | Tách reference/test-only examples |
| Thay canonical example âm thầm | Người dùng không tái tạo được kết quả cũ | Review và changelog |

## 25. Ví dụ tổng hợp: bộ ví dụ chuẩn cho DSL đơn hàng

Một dự án thực hành có thể chọn domain Order Management và tạo bộ ví dụ:

~~~text
examples/order-management/
├── 01-domain-model/
│   ├── customer.dsl
│   ├── product.dsl
│   └── order.dsl
├── 02-validation/
│   ├── valid-order.dsl
│   └── invalid-order.dsl
├── 03-query/
│   ├── open-orders.dsl
│   └── order-pagination.dsl
├── 04-workflow/
│   ├── fulfill-order.dsl
│   └── payment-timeout.dsl
├── 05-api/
│   ├── order-api.dsl
│   └── order-events.dsl
├── 06-configuration/
│   ├── base-profile.dsl
│   └── production-profile.dsl
├── 07-codegen/
│   └── generated-order-service/
└── manifest.yml
~~~

### 25.1. Luồng học tập

Người học bắt đầu từ model Customer/Product/Order, sau đó thêm validation, query, workflow, API và profile. Mỗi bước sử dụng model trước để cho thấy các tính năng DSL phối hợp.

### 25.2. Expected outputs

Mỗi folder có thể chứa expected AST snapshot, diagnostics, query result hoặc generated output. CI chạy toàn bộ ví dụ để xác nhận.

### 25.3. Negative cases

invalid-order.dsl có thể minh họa quantity âm hoặc customer ID chưa resolve. payment-timeout.dsl minh họa event không đến đúng hạn.

### 25.4. End-to-end

Ví dụ fulfill-order có thể dùng mock payment và inventory services để chạy toàn bộ workflow mà không gọi hệ thống thật.

### 25.5. Canonical status

Manifest có thể đánh dấu những ví dụ dùng trong tutorial, những ví dụ dùng trong reference và những fixture chỉ dành cho test compiler.

## 26. Mẫu manifest cho example catalog

Một manifest có thể mô tả:

~~~yaml
examples:
  - id: order-domain-model
    title: Order domain model
    level: beginner
    status: canonical
    dslVersion: "2.x"
    features:
      - module
      - entity
      - type
    source:
      - 01-domain-model/order.dsl
    checks:
      - parse
      - ast-snapshot
    expected:
      - 01-domain-model/expected/order.ast

  - id: fulfill-order-workflow
    title: Fulfill an order
    level: advanced
    status: canonical
    dslVersion: "2.x"
    features:
      - workflow
      - event
      - timeout
    source:
      - 04-workflow/fulfill-order.dsl
    checks:
      - parse
      - semantic
      - integration
~~~

Manifest giúp tool tự động tìm source, chọn test và tạo catalog page. Schema manifest cần được version hóa để tooling có thể đọc ổn định.

## 27. Nguyên tắc xác định ví dụ chuẩn

Khi xây dựng bộ ví dụ cho dự án DSL, có thể áp dụng các nguyên tắc sau:

1. **Bắt đầu từ use case.** Ví dụ phải thể hiện vấn đề thật mà DSL giải quyết.
2. **Phân loại theo mục tiêu.** Tách minimal, feature, end-to-end, error và integration examples.
3. **Lập ma trận coverage.** Bao phủ grammar, semantics, runtime, tooling và deployment.
4. **Giữ ví dụ nhỏ và đủ context.** Không thêm chi tiết không phục vụ mục tiêu.
5. **Có expected behavior.** Người đọc và CI biết kết quả đúng là gì.
6. **Dùng domain xuyên suốt có thể mở rộng.** Giúp liên kết các chương và tính năng.
7. **Bao gồm negative cases.** Giải thích lỗi và cách sửa.
8. **Duy trì executable examples.** Parse/build/run trong CI khi phù hợp.
9. **Gắn version và owner.** Biết ví dụ thuộc release nào và ai chịu trách nhiệm.
10. **Tái sử dụng cùng source.** Docs, tests và workshop không nên giữ bản sao lệch nhau.
11. **Bảo đảm an toàn.** Synthetic data, sandbox, no secrets và cleanup.
12. **Review thay đổi canonical.** Xem xét impact đến người học và compatibility.
13. **Đo maintenance cost.** Loại bỏ ví dụ không còn giá trị hoặc không thể duy trì.
14. **Giữ learning path rõ.** Tăng độ khó từng bước và nêu prerequisite.

## 28. Kết luận

Xác định ví dụ chuẩn là việc chọn và quản lý một tập mẫu đại diện cho cú pháp, semantics và use case của DSL. Ví dụ chuẩn giúp nhóm thống nhất thiết kế, hỗ trợ người học, làm fixture cho parser/compiler và xác minh behavior của sản phẩm. Chúng cần có mục tiêu rõ, source hợp lệ, expected result, version, dependencies và cách kiểm tra.

Một bộ ví dụ tốt kết hợp minimal syntax examples, feature examples, negative cases, end-to-end projects và integration scenarios. Domain xuyên suốt giúp người học thấy các phần DSL kết nối với nhau; ma trận coverage bảo đảm các tính năng quan trọng không bị bỏ sót. Khi examples được chạy tự động, quản lý như code và review cùng release, tài liệu không bị tách rời implementation.

Trong dự án thực hành, canonical examples còn là tiêu chí để đánh giá thiết kế ngôn ngữ: DSL có diễn đạt use case tự nhiên không, người dùng hiểu kết quả không và các thành phần compiler/runtime có phối hợp được không. Chọn đúng ví dụ ngay từ đầu giúp nhóm xây sản phẩm có thể học, kiểm thử và mở rộng lâu dài.
