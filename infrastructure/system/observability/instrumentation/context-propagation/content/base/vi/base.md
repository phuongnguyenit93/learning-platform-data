# Observability Instrumentation Context Propagation

Context propagation giúp các thành phần trong cùng luồng xử lý giữ được thông tin liên kết khi một yêu cầu chuyển thread, chạy bất đồng bộ hoặc đi qua nhiều dịch vụ. Nhờ đó, log và distributed trace có thể được đối chiếu theo cùng một ngữ cảnh, kể cả khi ứng dụng dùng HTTP, message broker hay Reactor.

Module này dành cho lập trình viên Java/Spring Boot đã có kiến thức cơ bản về logging và tracing. Trọng tâm là phân biệt trace context, baggage và MDC; quản lý `Context`/`Scope` đúng vòng đời; và truyền ngữ cảnh qua Executor, `CompletableFuture`, Reactor cùng các giao tiếp giữa dịch vụ.

Lộ trình bắt đầu từ nguyên lý và chuẩn Trace Context, tiếp tục với các kỹ thuật truyền ngữ cảnh trong ứng dụng và qua mạng, rồi kết thúc bằng kiểm thử tính liên tục, cô lập context và bảo vệ dữ liệu. Sau khi học, bạn có thể xác định chỗ context bị mất, khắc phục việc tách rời log–trace và hạn chế rò rỉ dữ liệu qua baggage.