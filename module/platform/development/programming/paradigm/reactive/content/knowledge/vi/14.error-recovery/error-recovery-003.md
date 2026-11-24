# Chuyển đổi lỗi nhưng giữ nguyên nguyên nhân ban đầu

Trong một pipeline reactive, lỗi thường đi qua nhiều tầng: thư viện I/O phát sinh lỗi kỹ thuật, adapter chuyển lỗi thành tín hiệu reactive, service diễn giải lỗi theo nghiệp vụ và tầng API quyết định cách phản hồi cho người gọi. Mỗi tầng có thể cần một kiểu exception dễ hiểu hơn đối với trách nhiệm của mình. Khi chuyển đổi lỗi, cần giữ lại nguyên nhân ban đầu để không làm mất thông tin chẩn đoán.

Bài học thuộc chương **Lỗi và phục hồi** của module **REACTIVE_PROGRAMMING**. Module hướng dẫn tư duy theo các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và backpressure của Reactive Streams; người học thực hành **Mono**, **Flux**, kết hợp toán tử, kiểm soát scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java. Với Project Reactor, toán tử **onErrorMap** cho phép chuyển một tín hiệu lỗi thành exception phù hợp hơn với tầng hiện tại, đồng thời giữ nguyên exception gốc làm **cause**.

## Vì sao cần chuyển đổi lỗi?

Một thư viện đọc tệp có thể phát sinh **IOException**. Tầng nghiệp vụ không nhất thiết muốn để kiểu lỗi I/O xuất hiện trực tiếp trong hợp đồng của service. Service có thể diễn giải nó thành **DocumentReadException**, còn tầng ứng dụng có thể phân loại lỗi đó để ghi log, trả mã lỗi hoặc quyết định có thể thử lại hay không.

Chuyển đổi lỗi giúp mỗi tầng sử dụng ngôn ngữ phù hợp với trách nhiệm của mình:

- Tầng tích hợp mô tả lỗi kỹ thuật như lỗi kết nối, lỗi I/O hoặc lỗi giao thức.
- Tầng nghiệp vụ mô tả thao tác thất bại như không thể tải hồ sơ hoặc không thể đọc tài liệu.
- Tầng giao tiếp bên ngoài ánh xạ lỗi nghiệp vụ thành mã trạng thái hoặc cấu trúc phản hồi.

Nếu chỉ tạo exception mới bằng thông điệp của lỗi cũ, thông tin về kiểu lỗi, stack trace và dữ liệu chẩn đoán có thể bị mất. Ví dụ sau không giữ nguyên nguyên nhân:

~~~java
.onErrorMap(error -> new RuntimeException(error.getMessage()))
~~~

Exception mới chỉ chứa thông điệp được sao chép. Nó không biết exception nào đã gây ra lỗi, nên **getCause()** trả về **null** và stack trace của lỗi gốc không còn nằm trong chuỗi nguyên nhân.

Hãy truyền exception gốc vào constructor của exception mới:

~~~java
.onErrorMap(error ->
    new DocumentReadException("Không thể đọc tài liệu", error)
)
~~~

Constructor này cần gọi **super(message, cause)**. Khi đó, exception mới có thể cung cấp ngữ cảnh nghiệp vụ, còn **getCause()** giữ tham chiếu tới exception ban đầu.

## Chuyển lỗi bằng onErrorMap

**onErrorMap** nhận một hàm chuyển đổi **Throwable** thành **Throwable**. Khi upstream phát **onError**, hàm được gọi và exception trả về trở thành lỗi mà downstream nhận được.

Ví dụ, tạo exception miền cho thao tác đọc tài liệu:

~~~java
public final class DocumentReadException extends RuntimeException {
    private final String documentId;

    public DocumentReadException(String documentId, Throwable cause) {
        super("Không thể đọc tài liệu: " + documentId, cause);
        this.documentId = documentId;
    }

    public String documentId() {
        return documentId;
    }
}
~~~

Adapter có thể chuyển **IOException** thành lỗi miền:

~~~java
Mono<String> readDocument(Path path, String documentId) {
    return Mono.fromCallable(() -> Files.readString(path))
        .subscribeOn(Schedulers.boundedElastic())
        .onErrorMap(IOException.class,
            cause -> new DocumentReadException(documentId, cause));
}
~~~

Ở đây:

1. **Mono.fromCallable** trì hoãn thao tác đọc tệp đến khi subscribe và chuyển exception được ném thành tín hiệu **onError**.
2. **subscribeOn(Schedulers.boundedElastic())** cô lập lời gọi I/O đồng bộ khỏi thread xử lý sự kiện.
3. **onErrorMap(IOException.class, ...)** chỉ chuyển các lỗi thuộc kiểu **IOException** thành **DocumentReadException**.
4. Exception mới giữ **IOException** làm nguyên nhân bằng cách truyền **cause** vào constructor.

Các lỗi khác không khớp với **IOException.class** tiếp tục đi xuống dưới với kiểu ban đầu. Ví dụ, một **IllegalArgumentException** do tham số không hợp lệ không bị đổi thành lỗi đọc tệp chỉ vì nó xuất hiện trong cùng pipeline.

## Chọn phạm vi lỗi cần chuyển đổi

Reactor cung cấp các dạng **onErrorMap** thường dùng:

| Dạng gọi | Ý nghĩa | Khi sử dụng |
|---|---|---|
| **onErrorMap(mapper)** | Chuyển mọi lỗi được truyền đến toán tử | Mọi lỗi tại ranh giới này đều cần một kiểu lỗi chung |
| **onErrorMap(ExceptionType.class, mapper)** | Chỉ chuyển lỗi thuộc kiểu đã chỉ định | Chuyển lỗi kỹ thuật cụ thể như **IOException** |
| **onErrorMap(predicate, mapper)** | Chuyển lỗi thỏa điều kiện | Cần phân loại theo thuộc tính hoặc nhóm lỗi |

Ví dụ chỉ chuyển lỗi kết nối:

~~~java
Mono<Account> account = accountClient.fetch(accountId)
    .onErrorMap(
        error -> error instanceof ConnectException,
        error -> new AccountServiceUnavailableException(accountId, error)
    );
~~~

Phạm vi càng cụ thể thì hợp đồng lỗi càng dễ dự đoán. Tránh chuyển mọi **Throwable** thành một exception nghiệp vụ duy nhất nếu các lỗi như lỗi lập trình, lỗi xác thực đầu vào và lỗi hạ tầng cần được xử lý khác nhau.

Không nên xem việc chuyển đổi lỗi là cách sửa một lỗi không mong muốn. **onErrorMap** chỉ thay đổi kiểu và ngữ cảnh của tín hiệu lỗi; nó không làm thao tác thất bại trở thành thành công và cũng không tự khởi động lại Publisher.

## Chuỗi nguyên nhân và stack trace

Trong Java, **Throwable** hỗ trợ quan hệ nguyên nhân thông qua **getCause()**. Khi một exception mới bọc exception cũ, ta có thể đi theo chuỗi nguyên nhân để tìm lỗi ban đầu.

~~~java
public final class AccountLoadException extends RuntimeException {
    public AccountLoadException(String accountId, Throwable cause) {
        super("Không thể tải tài khoản " + accountId, cause);
    }
}

public final class AccountServiceException extends RuntimeException {
    public AccountServiceException(Throwable cause) {
        super("Dịch vụ tài khoản không hoàn thành thao tác", cause);
    }
}
~~~

Các tầng có thể bổ sung ngữ cảnh theo từng trách nhiệm:

~~~java
Mono<Account> account = repository.findById(accountId)
    .onErrorMap(
        RepositoryException.class,
        cause -> new AccountLoadException(accountId, cause)
    )
    .onErrorMap(
        AccountLoadException.class,
        cause -> new AccountServiceException(cause)
    );
~~~

Khi lỗi đi xuống downstream, cấu trúc có thể là:

~~~text
AccountServiceException
  caused by AccountLoadException
    caused by RepositoryException
      caused by IOException hoặc lỗi driver
~~~

Stack trace của exception bọc mới cho biết nơi nó được tạo ra. Stack trace của exception gốc vẫn nằm trong **cause**, vì vậy log đầy đủ exception sẽ giúp người vận hành lần theo nơi lỗi thực sự phát sinh.

Một số nguyên tắc khi xây dựng chuỗi nguyên nhân:

- Luôn truyền **cause** vào constructor của exception bọc nếu có nguyên nhân cụ thể.
- Không chỉ sao chép **cause.getMessage()** rồi bỏ mất chính đối tượng exception.
- Không thay thế một exception đã có ngữ cảnh bằng một exception chung chung ở mọi tầng.
- Giữ các thuộc tính nghiệp vụ cần thiết, chẳng hạn mã tài liệu hoặc mã tài khoản, trong exception miền nếu tầng xử lý cần chúng.
- Tránh đưa thông tin nhạy cảm như token, mật khẩu hoặc nội dung tài liệu vào thông điệp lỗi.

**cause** và **suppressed exception** có mục đích khác nhau. **cause** diễn tả lỗi này được tạo ra do lỗi nào. **suppressed** thường ghi nhận lỗi phụ xảy ra trong quá trình đóng tài nguyên hoặc khi xử lý một lỗi khác. Không nên dùng **addSuppressed** thay cho constructor nhận **cause** khi đang bọc một lỗi chính.

## Chuyển lỗi ở đúng ranh giới

Không nhất thiết phải bọc lại exception tại mọi toán tử. Nếu mỗi tầng đều tạo một lớp wrapper mà không bổ sung ngữ cảnh hữu ích, chuỗi lỗi sẽ dài và khó đọc. Hãy chuyển lỗi tại ranh giới nơi kiểu exception kỹ thuật cần được diễn giải thành một hợp đồng có ý nghĩa hơn.

Ví dụ, adapter có thể chuyển lỗi thư viện:

~~~java
Mono<Profile> fetchProfile(String userId) {
    return legacyClient.fetchProfile(userId)
        .onErrorMap(
            LegacyTransportException.class,
            cause -> new ProfileGatewayException(userId, cause)
        );
}
~~~

Service có thể giữ nguyên **ProfileGatewayException** nếu đó đã là kiểu lỗi phù hợp với hợp đồng của service. Tầng API sau đó quyết định cách biểu diễn lỗi cho client mà không cần thay đổi chuỗi nguyên nhân.

Có thể dùng **doOnError** để quan sát lỗi mà không thay đổi tín hiệu:

~~~java
Mono<Profile> profile = fetchProfile(userId)
    .doOnError(error -> metrics.recordProfileFailure(userId, error))
    .onErrorMap(
        ProfileGatewayException.class,
        cause -> new ProfileUnavailableException(userId, cause)
    );
~~~

**doOnError** thực hiện tác vụ phụ như ghi metric hoặc log; exception truyền xuống vẫn là exception upstream. **onErrorMap** mới là toán tử thay đổi exception được downstream nhận. Nên tránh ghi cùng một lỗi ở mọi tầng, vì log lặp lại có thể gây nhiễu và làm tăng chi phí vận hành.

Đối với chẩn đoán assembly của Reactor, **checkpoint()** có thể bổ sung thông tin về vị trí lắp ráp pipeline vào stack trace khi có lỗi:

~~~java
Mono<Profile> profile = fetchProfile(userId)
    .checkpoint("profile-service.fetch");
~~~

**checkpoint** hỗ trợ tìm vị trí pipeline liên quan đến lỗi; nó không thay thế việc giữ **cause** và cũng không chuyển kiểu exception. Có thể cân nhắc checkpoint có stack trace đầy đủ ở những ranh giới cần chẩn đoán sâu, vì việc thu thập stack trace có chi phí.

## Phân biệt chuyển đổi lỗi với phục hồi lỗi

**onErrorMap** và **onErrorResume** đều phản ứng với **onError**, nhưng mục tiêu khác nhau:

| Toán tử | Hành vi | Tín hiệu downstream |
|---|---|---|
| **onErrorMap** | Tạo exception khác, thường bọc lỗi gốc | Vẫn là **onError**, với exception đã chuyển đổi |
| **onErrorResume** | Đăng ký Publisher thay thế | Có thể phát dữ liệu hoặc hoàn tất bình thường |
| **doOnError** | Thực hiện tác vụ quan sát | Giữ nguyên exception và tín hiệu lỗi |

Ví dụ chuyển lỗi để bổ sung ngữ cảnh:

~~~java
Mono<Profile> profile = fetchProfile(userId)
    .onErrorMap(cause ->
        new ProfileLoadException(userId, cause)
    );
~~~

Publisher vẫn kết thúc bằng lỗi. Nếu tầng gọi cần fallback, nó có thể tiếp tục dùng **onErrorResume**:

~~~java
Mono<Profile> profile = fetchProfile(userId)
    .onErrorMap(
        ProfileGatewayException.class,
        cause -> new ProfileLoadException(userId, cause)
    )
    .onErrorResume(ProfileLoadException.class,
        error -> profileCache.find(userId));
~~~

Ở ví dụ này, lỗi được diễn giải trước, sau đó một lỗi miền cụ thể được dùng để chọn fallback. Nếu fallback cũng lỗi, lỗi mới của fallback được truyền xuống; lỗi ban đầu không tự động trở thành nguyên nhân của lỗi fallback. Nếu cần lưu lịch sử thất bại của nguồn chính, hãy ghi nhận nó trong log, metric hoặc kiểu kết quả miền trước khi chuyển sang fallback.

Không nên dùng **onErrorResume** chỉ để đổi kiểu exception. Ngược lại, cũng không nên dùng **onErrorMap** khi mục tiêu thật sự là thử nguồn khác hoặc trả kết quả mặc định.

## Cancellation không phải là một exception để chuyển đổi

**onErrorMap** chỉ xử lý tín hiệu **onError**. Khi downstream hủy subscription, đó là tín hiệu cancellation trong giao thức reactive, không phải một exception được gửi qua **onError**. Vì vậy, không thể dùng **onErrorMap** để bắt cancellation hoặc chuyển nó thành lỗi nghiệp vụ.

Nếu cần giải phóng tài nguyên khi hoàn tất, lỗi hoặc bị hủy, hãy dùng cơ chế cleanup phù hợp như **doFinally** hoặc **using/usingWhen** tùy loại tài nguyên. **doFinally** nhận **SignalType** để phân biệt **ON_COMPLETE**, **ON_ERROR** và **CANCEL**:

~~~java
Mono<Data> data = loadData()
    .doFinally(signalType -> {
        if (signalType == SignalType.CANCEL) {
            metrics.recordCancelledLoad();
        }
    });
~~~

Đừng chuyển cancellation thành **onError** để tiện xử lý chung. Làm như vậy có thể khiến tầng gọi ghi nhận một thao tác bị hủy như một lần thất bại, kích hoạt retry không cần thiết hoặc tạo side effect sau khi người gọi đã ngừng quan tâm.

## Kiểm thử việc giữ nguyên nguyên nhân bằng StepVerifier

Một kiểm thử cần xác nhận cả kiểu exception mới và tham chiếu đến nguyên nhân ban đầu. Chỉ kiểm tra thông điệp lỗi là chưa đủ.

~~~java
IOException original = new IOException("disk unavailable");

Mono<String> source = Mono.<String>error(original)
    .onErrorMap(
        IOException.class,
        cause -> new DocumentReadException("doc-42", cause)
    );

StepVerifier.create(source)
    .expectErrorSatisfies(error -> {
        assertInstanceOf(DocumentReadException.class, error);
        assertEquals("doc-42",
            ((DocumentReadException) error).documentId());
        assertSame(original, error.getCause());
    })
    .verify();
~~~

**assertSame** kiểm tra **cause** chính là đối tượng exception ban đầu, không phải một exception khác chỉ có cùng thông điệp. Điều này xác nhận chuỗi nguyên nhân giữ được danh tính và stack trace của lỗi gốc.

Có thể kiểm tra rằng lỗi ngoài phạm vi chuyển đổi được giữ nguyên:

~~~java
IllegalStateException original =
    new IllegalStateException("invalid state");

Mono<String> source = Mono.<String>error(original)
    .onErrorMap(
        IOException.class,
        cause -> new DocumentReadException("doc-42", cause)
    );

StepVerifier.create(source)
    .expectErrorMatches(error -> error == original)
    .verify();
~~~

Kiểm thử này bảo đảm bộ lọc kiểu của **onErrorMap** không làm thay đổi các lỗi không thuộc nhóm cần chuyển đổi.

Với chuỗi nhiều tầng, hãy kiểm tra từng mắt xích:

~~~java
StepVerifier.create(service.loadAccount("A-17"))
    .expectErrorSatisfies(error -> {
        assertInstanceOf(AccountServiceException.class, error);
        Throwable accountCause = error.getCause();
        assertInstanceOf(AccountLoadException.class, accountCause);
        assertInstanceOf(RepositoryException.class,
            accountCause.getCause());
    })
    .verify();
~~~

Kiểu cụ thể trong kiểm thử phụ thuộc hợp đồng exception của ứng dụng. Mục tiêu là bảo đảm mỗi tầng bổ sung đúng ngữ cảnh và không làm đứt chuỗi nguyên nhân.

## Những lỗi thường gặp

| Cách làm | Hậu quả | Cách xử lý |
|---|---|---|
| Tạo exception mới chỉ từ **getMessage()** | Mất tham chiếu và stack trace của lỗi gốc | Truyền lỗi cũ vào constructor dưới dạng **cause** |
| Dùng **onErrorMap** cho mọi **Throwable** | Có thể che lấp lỗi lập trình hoặc lỗi không thuộc trách nhiệm của tầng | Lọc theo kiểu hoặc predicate cụ thể |
| Bọc lại lỗi ở mọi toán tử | Chuỗi exception dài nhưng không có thêm thông tin | Chuyển lỗi tại ranh giới có ý nghĩa |
| Dùng **onErrorMap** với mục đích phục hồi | Pipeline vẫn kết thúc bằng **onError** | Dùng **onErrorResume** nếu cần Publisher thay thế |
| Dùng **doOnError** nhưng mong exception đổi kiểu | Downstream vẫn nhận lỗi ban đầu | Dùng **onErrorMap** để chuyển exception |
| Xem cancellation là lỗi | Có thể kích hoạt retry hoặc log thất bại sai | Xử lý cancellation bằng **doFinally** và cleanup |

## Nguyên tắc áp dụng

Trước khi chuyển đổi một lỗi trong pipeline, hãy xác định:

1. Lỗi gốc thuộc tầng kỹ thuật nào và tầng hiện tại cần diễn giải nó ra sao?
2. Chỉ nhóm exception nào được phép chuyển đổi?
3. Exception mới có constructor giữ **cause** hay không?
4. Tầng hiện tại có bổ sung ngữ cảnh hữu ích như mã tài nguyên hoặc thao tác thất bại không?
5. Mục tiêu là đổi kiểu lỗi, quan sát lỗi hay phục hồi bằng Publisher khác?
6. Kiểm thử có xác nhận được cả exception mới lẫn chuỗi nguyên nhân không?

**onErrorMap** giúp giữ hợp đồng lỗi nhất quán khi pipeline đi qua nhiều tầng. Bằng cách truyền exception gốc làm **cause**, chọn đúng phạm vi lỗi và kiểm thử chuỗi nguyên nhân, ứng dụng vẫn có thể cung cấp thông tin nghiệp vụ dễ hiểu mà không đánh mất dữ liệu cần thiết để chẩn đoán sự cố.
