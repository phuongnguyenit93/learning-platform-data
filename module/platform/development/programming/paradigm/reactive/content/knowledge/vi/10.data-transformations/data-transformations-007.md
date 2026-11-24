# Tách phần dữ liệu hợp lệ và biểu diễn lỗi xác thực

Trong module `REACTIVE_PROGRAMMING`, ta xây dựng các pipeline bất đồng bộ dựa trên hợp đồng Publisher–Subscriber và backpressure của Reactive Streams, đồng thời thực hành `Mono`, `Flux`, toán tử, scheduler, xử lý lỗi và kiểm thử trong hệ sinh thái Java. Khi một luồng chứa nhiều bản ghi đầu vào, không phải bản ghi nào cũng thỏa mãn quy tắc nghiệp vụ. Pipeline cần xác định bản ghi nào hợp lệ, bản ghi nào bị từ chối và lý do từ chối để hệ thống có thể tiếp tục xử lý dữ liệu tốt mà vẫn lưu lại thông tin cần sửa.

Điểm cần phân biệt là **lỗi xác thực của một bản ghi** thường là kết quả nghiệp vụ của việc kiểm tra dữ liệu, còn **tín hiệu `onError`** biểu thị subscription đã thất bại và kết thúc. Nếu dùng `onError` cho mọi bản ghi sai, một lỗi xác thực có thể làm dừng toàn bộ luồng. Cách phù hợp thường là biểu diễn kết quả xác thực thành dữ liệu, rồi tách nhánh hợp lệ và không hợp lệ bằng các toán tử của Reactor.

## 1. Phân biệt lỗi xác thực và lỗi của pipeline

Giả sử hệ thống nhận một luồng yêu cầu tạo khách hàng. Mỗi yêu cầu cần có email đúng định dạng và tuổi nằm trong phạm vi cho phép. Có ba trường hợp khác nhau:

- Bản ghi thiếu email hoặc tuổi không hợp lệ: dữ liệu đến được hệ thống nhưng không thỏa mãn quy tắc nghiệp vụ. Ta cần trả về lỗi xác thực gắn với bản ghi đó.
- Dịch vụ kiểm tra bên ngoài không truy cập được hoặc cơ sở dữ liệu ngừng hoạt động: pipeline không thể thực hiện công việc. Đây là lỗi vận hành có thể được truyền bằng `onError`.
- Bản ghi hợp lệ: tiếp tục sang bước lưu hoặc xử lý tiếp theo.

| Tình huống | Cách biểu diễn phù hợp | Luồng có thể tiếp tục? |
|---|---|---|
| Một trường sai quy tắc | Kết quả xác thực không hợp lệ, chứa danh sách lỗi | Có, với các bản ghi khác |
| Một bản ghi hợp lệ | Kết quả xác thực hợp lệ, chứa giá trị đã kiểm tra | Có |
| Dịch vụ xác thực bị lỗi | `onError` hoặc một kiểu kết quả lỗi vận hành nếu nghiệp vụ yêu cầu cách ly từng bản ghi | Mặc định không, nếu lỗi không được phục hồi |
| Lỗi lập trình không mong đợi | Để lỗi được truyền rõ ràng và xử lý ở ranh giới phù hợp | Thường kết thúc subscription |

Reactive Streams định nghĩa `onError` là tín hiệu kết thúc. Sau tín hiệu này, subscription không phát thêm `onNext` hoặc `onComplete`. Vì vậy, nếu cần thu thập nhiều lỗi xác thực trong cùng một batch, hãy coi chúng là phần dữ liệu của kết quả, thay vì biến từng lỗi thành tín hiệu kết thúc.

## 2. Biểu diễn kết quả xác thực thành dữ liệu

Một kết quả xác thực nên giữ lại đầu vào, giá trị được chấp nhận nếu hợp lệ và danh sách lỗi nếu không hợp lệ. Cách biểu diễn này cho phép downstream biết bản ghi nào bị từ chối và vì sao.

```java
record ValidationIssue(
    String field,
    String code,
    String message
) {}

record ValidationResult<T>(
    T input,
    Optional<T> acceptedValue,
    List<ValidationIssue> issues
) {
    ValidationResult {
        acceptedValue = Objects.requireNonNull(acceptedValue);
        issues = List.copyOf(issues);
    }

    boolean isValid() {
        return issues.isEmpty();
    }

    static <T> ValidationResult<T> valid(T value) {
        return new ValidationResult<>(value, Optional.of(value), List.of());
    }

    static <T> ValidationResult<T> invalid(
            T input,
            List<ValidationIssue> issues) {
        if (issues.isEmpty()) {
            throw new IllegalArgumentException("Phải có ít nhất một lỗi xác thực");
        }
        return new ValidationResult<>(input, Optional.empty(), issues);
    }
}
```

`Optional<T>` giúp tránh dùng `null` để biểu diễn việc không có giá trị được chấp nhận. `issues` chứa mọi lỗi phát hiện trên bản ghi, không chỉ lỗi đầu tiên. Hàm `isValid()` dựa vào danh sách lỗi để xác định trạng thái. Trong ứng dụng thực tế, có thể bổ sung mã bản ghi, thời điểm kiểm tra, phiên bản quy tắc hoặc nguồn dữ liệu để hỗ trợ truy vết.

Ví dụ một bộ kiểm tra khách hàng:

```java
ValidationResult<Customer> validateCustomer(Customer customer) {
    List<ValidationIssue> issues = new ArrayList<>();

    if (customer.email() == null || !customer.email().contains("@")) {
        issues.add(new ValidationIssue(
            "email", "EMAIL_INVALID", "Email không hợp lệ"
        ));
    }

    if (customer.age() < 18) {
        issues.add(new ValidationIssue(
            "age", "AGE_TOO_LOW", "Khách hàng phải từ 18 tuổi"
        ));
    }

    if (!issues.isEmpty()) {
        return ValidationResult.invalid(customer, issues);
    }

    return ValidationResult.valid(customer);
}
```

Đoạn kiểm tra có thể thu thập nhiều lỗi trên cùng một bản ghi. Quy tắc được thực hiện đồng bộ và không ném ngoại lệ cho trường hợp dữ liệu không hợp lệ. Nếu đầu vào vi phạm quy tắc, hàm trả về một `ValidationResult` mang các lỗi đó.

## 3. Xác thực từng phần tử trong `Flux`

Khi có một `Flux<Customer>`, dùng `map` để biến mỗi bản ghi thành một kết quả xác thực:

```java
Flux<ValidationResult<Customer>> outcomes = customers
    .map(this::validateCustomer);
```

Đây là phép biến đổi một-một: mỗi phần tử đầu vào tạo ra một `ValidationResult`. Bản ghi sai quy tắc vẫn tạo ra một phần tử đầu ra, vì lỗi xác thực đang được biểu diễn bằng dữ liệu. Do đó, một bản ghi không hợp lệ không làm kết thúc subscription và các bản ghi sau vẫn được kiểm tra.

Nếu dùng `filter` trực tiếp:

```java
Flux<Customer> validCustomers = customers
    .filter(this::isValid);
```

những bản ghi không hợp lệ bị loại bỏ mà không giữ lại lý do. Cách này chỉ phù hợp khi việc bỏ qua dữ liệu sai là chủ đích và không cần báo cáo lỗi. Nếu cần kiểm toán, trả lỗi cho người gửi hoặc cho phép sửa dữ liệu, hãy giữ kết quả xác thực trước khi tách nhánh.

## 4. Tách dữ liệu hợp lệ và không hợp lệ

Sau khi có `Flux<ValidationResult<T>>`, có thể tạo hai nhánh bằng `filter`:

```java
Flux<Customer> validCustomers = outcomes
    .filter(ValidationResult::isValid)
    .map(result -> result.acceptedValue().orElseThrow());

Flux<ValidationResult<Customer>> rejectedCustomers = outcomes
    .filter(result -> !result.isValid());
```

Nhánh hợp lệ chỉ phát giá trị được chấp nhận; nhánh bị từ chối giữ cả bản ghi gốc và danh sách lỗi. Tuy nhiên, hai biến trên cùng tham chiếu đến Publisher `outcomes`. Nếu `outcomes` là nguồn lạnh, đăng ký độc lập vào hai nhánh có thể khiến quá trình xác thực upstream chạy hai lần. Với nguồn có side effect như gọi dịch vụ hoặc ghi log, điều này có thể gây kết quả khác nhau hoặc lặp công việc.

Khi cần tiêu thụ đồng thời hai nhánh từ một lần chạy upstream, dùng `publish` với một hàm biến đổi để chia sẻ một subscription:

```java
record ValidationReport<T>(
    List<T> accepted,
    List<ValidationResult<T>> rejected
) {}

Mono<ValidationReport<Customer>> report = outcomes.publish(shared -> {
    Mono<List<Customer>> accepted = shared
        .filter(ValidationResult::isValid)
        .map(result -> result.acceptedValue().orElseThrow())
        .collectList();

    Mono<List<ValidationResult<Customer>>> rejected = shared
        .filter(result -> !result.isValid())
        .collectList();

    return Mono.zip(accepted, rejected)
        .map(tuple -> new ValidationReport<>(
            tuple.getT1(), tuple.getT2()
        ));
});
```

Hàm biến đổi của `publish` cho phép nhiều nhánh cùng tiêu thụ một nguồn upstream. `Mono.zip` đợi cả hai nhánh hoàn tất rồi ghép danh sách hợp lệ và danh sách bị từ chối thành một báo cáo. Cách này hữu ích với batch có kích thước vừa phải và khi cần trả về một kết quả tổng hợp.

`collectList()` giữ tất cả phần tử của nhánh trong bộ nhớ cho đến khi nguồn hoàn tất. Không nên dùng cách tổng hợp này cho một luồng vô hạn hoặc batch quá lớn. Với luồng dài, hãy ghi từng kết quả vào kho dữ liệu, hàng đợi hoặc sink có giới hạn thay vì gom toàn bộ vào một danh sách.

## 5. Lưu riêng hai nhánh trong một lần chạy

Trong xử lý dữ liệu thực tế, thường cần lưu bản ghi hợp lệ vào kho chính và lưu bản ghi bị từ chối vào kho lỗi để người dùng có thể xem hoặc sửa. Có thể dùng cùng kỹ thuật chia sẻ nguồn:

```java
Mono<Void> routeResults = outcomes.publish(shared -> Mono.when(
    shared
        .filter(ValidationResult::isValid)
        .concatMap(result -> acceptedRepository.save(
            result.acceptedValue().orElseThrow()
        ))
        .then(),

    shared
        .filter(result -> !result.isValid())
        .concatMap(rejectedRepository::save)
        .then()
));
```

Ở đây, mỗi nhánh tiêu thụ các kết quả thuộc nhóm của nó. `concatMap` thực hiện thao tác lưu theo thứ tự và chỉ chuyển sang phần tử tiếp theo khi Publisher lưu trước đó hoàn tất. `Mono.when` đợi cả hai nhánh hoàn tất. `publish` chia sẻ một subscription upstream để không chạy xác thực hai lần.

Nếu thứ tự giữa các nhánh có ý nghĩa nghiệp vụ, cần thiết kế thêm một bước điều phối hoặc ghi nhận trạng thái nhất quán. Hai nhánh được xử lý độc lập nên không có bảo đảm rằng bản ghi hợp lệ và bản ghi lỗi sẽ được lưu theo thứ tự xen kẽ ban đầu. Nếu cần thứ tự toàn cục, có thể lưu kết quả xác thực vào một kho trung gian theo sequence number rồi xử lý tuần tự.

## 6. Xác thực bất đồng bộ

Một số quy tắc xác thực cần gọi dịch vụ bên ngoài, chẳng hạn kiểm tra mã khách hàng, xác nhận địa chỉ hoặc kiểm tra hạn mức. Khi đó, hàm xác thực có thể trả về `Mono<List<ValidationIssue>>` thay vì trả kết quả ngay lập tức.

```java
Flux<ValidationResult<Customer>> outcomes = customers.flatMap(
    customer -> ruleService.validate(customer)
        .map(issues -> issues.isEmpty()
            ? ValidationResult.valid(customer)
            : ValidationResult.invalid(customer, issues)),
    32
);
```

Tham số `32` giới hạn số phép xác thực bất đồng bộ được chạy đồng thời qua `flatMap`. Điều này giúp tránh khởi chạy quá nhiều request cùng lúc. `flatMap` có thể phát kết quả theo thứ tự hoàn tất, không nhất thiết theo thứ tự đầu vào. Nếu cần giữ thứ tự đầu vào trong khi vẫn cho phép xử lý đồng thời có giới hạn, cân nhắc `flatMapSequential`; nếu cần tuần tự hoàn toàn, dùng `concatMap`.

Lỗi nghiệp vụ do quy tắc phát hiện vẫn được trả về trong danh sách `issues`. Nếu dịch vụ xác thực không thể truy cập hoặc request thất bại, `ruleService.validate` có thể phát `onError`; theo mặc định, lỗi đó kết thúc pipeline. Nếu yêu cầu nghiệp vụ là cách ly lỗi vận hành theo từng bản ghi và tiếp tục với bản ghi khác, cần biểu diễn rõ trạng thái đó trong một kiểu kết quả riêng, ví dụ `ValidationServiceFailure`, cùng mã tương quan và chính sách retry. Không nên bắt mọi lỗi rồi biến thành “dữ liệu không hợp lệ”, vì lỗi vận hành không chứng minh bản ghi sai.

## 7. `handle` và giới hạn của việc lọc dữ liệu

Toán tử `handle` cho phép phát không hoặc một tín hiệu đầu ra cho mỗi phần tử nguồn trong một callback đồng bộ. Nó có thể hữu ích cho việc lọc hoặc biến đổi có điều kiện:

```java
Flux<Customer> validCustomers = customers.handle((customer, sink) -> {
    ValidationResult<Customer> result = validateCustomer(customer);
    if (result.isValid()) {
        sink.next(result.acceptedValue().orElseThrow());
    }
});
```

Ví dụ này chỉ phát khách hàng hợp lệ. Những bản ghi sai bị bỏ mà không tạo tín hiệu lỗi hay giữ danh sách lỗi. Nếu cần tách hai nhóm, `handle` một mình không tạo hai Publisher đầu ra; hãy phát `ValidationResult` làm dữ liệu trước rồi phân nhánh như các phần trên.

Không nên dùng `onErrorContinue` như một cơ chế xác thực cho từng phần tử. Toán tử này xử lý một số lỗi phát sinh từ toán tử upstream trong những ngữ cảnh nhất định, nhưng hành vi phụ thuộc toán tử và nguồn. Nó không tự cung cấp cấu trúc dữ liệu để lưu bản ghi sai, mã lỗi hay nhiều lỗi của cùng một bản ghi. Kết quả xác thực rõ ràng giúp hợp đồng downstream dễ hiểu và dễ kiểm thử hơn.

## 8. Kiểm thử việc tách hai nhóm

Với một batch nhỏ, có thể kiểm tra cả số lượng và nội dung hai nhóm:

```java
Flux<Customer> customers = Flux.just(
    new Customer("a@example.com", 25),
    new Customer("invalid-email", 17),
    new Customer("b@example.com", 31)
);

Mono<ValidationReport<Customer>> report = validateAndSplit(customers);

StepVerifier.create(report)
    .assertNext(result -> {
        assertEquals(2, result.accepted().size());
        assertEquals(1, result.rejected().size());
        assertEquals("invalid-email",
            result.rejected().get(0).input().email());
        assertTrue(result.rejected().get(0).issues().stream()
            .anyMatch(issue -> issue.code().equals("EMAIL_INVALID")));
    })
    .verifyComplete();
```

Kiểm thử này xác nhận bản ghi sai vẫn xuất hiện trong báo cáo cùng lý do cụ thể, trong khi các bản ghi hợp lệ vẫn được giữ lại. Ngoài ra, nên kiểm tra các trường hợp biên:

- Tất cả bản ghi đều hợp lệ: danh sách `rejected` rỗng.
- Tất cả bản ghi đều không hợp lệ: danh sách `accepted` rỗng.
- Một bản ghi có nhiều lỗi: mọi lỗi đều được giữ trong `issues`.
- Nguồn rỗng: báo cáo có hai danh sách rỗng và hoàn tất bình thường.
- Dịch vụ xác thực bất đồng bộ lỗi: pipeline phát `onError` hoặc tạo kiểu lỗi vận hành riêng theo chính sách đã chọn.
- Nguồn có side effect: xác nhận việc phân nhánh không khiến upstream chạy lặp ngoài ý muốn.

## 9. Chọn cách biểu diễn phù hợp

| Nhu cầu | Cách làm phù hợp | Điều cần chú ý |
|---|---|---|
| Chỉ cần bỏ qua bản ghi sai | `filter` hoặc `handle` | Không giữ lý do bị loại |
| Cần biết bản ghi nào sai và vì sao | `ValidationResult<T>` | Biểu diễn lỗi xác thực như dữ liệu |
| Cần trả báo cáo batch gồm hai danh sách | `publish` kết hợp `collectList` và `zip` | Chỉ phù hợp khi batch có giới hạn bộ nhớ |
| Cần lưu hợp lệ và lỗi vào hai kho | `publish` kết hợp hai nhánh tiêu thụ | Xác định thứ tự, tính nhất quán và backpressure |
| Xác thực cần gọi dịch vụ bất đồng bộ | `flatMap` với concurrency giới hạn | Phân biệt lỗi quy tắc với lỗi vận hành |
| Một lỗi vận hành của một bản ghi không được làm dừng batch | Kiểu kết quả có nhánh lỗi vận hành riêng | Không ngụy trang lỗi hệ thống thành lỗi dữ liệu |

Khi thiết kế pipeline, hãy giữ ranh giới rõ ràng: **dữ liệu không hợp lệ là một kết quả xác thực có cấu trúc; lỗi khiến pipeline không thể tiếp tục là một tín hiệu lỗi reactive**. Tách hai khái niệm này giúp luồng tiếp tục xử lý các bản ghi tốt, lưu lại đầy đủ lý do từ chối và giữ cho hành vi lỗi của hệ thống dễ dự đoán.
