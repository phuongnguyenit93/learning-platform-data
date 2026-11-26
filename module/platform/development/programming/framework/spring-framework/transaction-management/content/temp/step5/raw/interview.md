Bạn giải thích các tính chất ACID được database bảo đảm và vai trò của Spring Transaction Management trong việc điều phối giao dịch như thế nào?
Bạn phân biệt atomicity của một giao dịch Spring với tính nguyên tử của từng câu SQL như thế nào?
Bạn sẽ thiết kế một service tạo đơn hàng và cập nhật tồn kho trong cùng một transaction ra sao?
Bạn phân tích vì sao @Transactional không tự bảo đảm tính nhất quán khi service ghi hai database độc lập như thế nào?
Bạn giải thích consistency của database liên quan đến unique constraint và quy tắc nghiệp vụ trong Spring service ra sao?
Bạn sẽ quyết định ranh giới transaction ở service layer thay vì controller theo những tiêu chí nào?
Bạn phân biệt isolation của transaction với synchronization giữa các thread trong JVM như thế nào?
Bạn giải thích durability sau commit khác gì với việc client HTTP đã nhận được response thành công?
Bạn sẽ tổ chức transaction boundary để giảm thời gian giữ row locks trong một workflow nhiều bước ra sao?
Bạn phân tích vì sao transaction dài bao gồm lời gọi HTTP ngoài có thể gây cạn connection pool như thế nào?
Bạn sẽ xác định thao tác nào phải chung một transaction và thao tác nào nên tách thành bước bất đồng bộ ra sao?
Bạn phân biệt transaction database và cơ chế distributed lock trong ứng dụng nhiều instance như thế nào?
Bạn sẽ thiết kế idempotency key để không tạo đơn hàng trùng khi request được retry sau timeout ra sao?
Bạn phân tích vì sao transaction rollback không thể hoàn tác một email đã được gửi thành công như thế nào?
Bạn sẽ chọn transactional outbox khi cần phát sự kiện sau khi dữ liệu nghiệp vụ được commit như thế nào?
Bạn giải thích PlatformTransactionManager cung cấp những thao tác cốt lõi nào để quản lý imperative transaction?
Bạn phân biệt TransactionManager, PlatformTransactionManager và ReactiveTransactionManager theo abstraction và execution context như thế nào?
Bạn mô tả vai trò của TransactionDefinition khi mô tả propagation, isolation, timeout và read-only ra sao?
Bạn sẽ dùng DefaultTransactionDefinition để mở transaction programmatically với thuộc tính rõ ràng như thế nào?
Bạn giải thích TransactionStatus cho biết điều gì về transaction hiện tại và rollback-only flag?
Bạn phân biệt TransactionStatus.isNewTransaction với trường hợp tham gia transaction đang hoạt động như thế nào?
Bạn sẽ xác định khi nào TransactionStatus.hasSavepoint cho thấy một nested transaction đang dùng savepoint ra sao?
Bạn phân tích rủi ro tự gọi commit hoặc rollback trên TransactionStatus không thuộc ranh giới mình kiểm soát như thế nào?
Bạn mô tả đường gọi getTransaction, commit và rollback qua PlatformTransactionManager khi một method được advice ra sao?
Bạn sẽ xác định khi nào dùng DataSourceTransactionManager cho JDBC operations thay vì JpaTransactionManager ra sao?
Bạn phân biệt DataSourceTransactionManager với JdbcTransactionManager về khả năng xử lý exception như thế nào?
Bạn mô tả JpaTransactionManager phối hợp EntityManager và JDBC connection theo phạm vi transaction như thế nào?
Bạn sẽ lựa chọn JtaTransactionManager trong trường hợp nhiều XA resources cần transaction coordinator ra sao?
Bạn phân tích vì sao một DataSourceTransactionManager không thể tự phối hợp atomic commit giữa hai DataSources ra sao?
Bạn sẽ xử lý ApplicationContext có nhiều PlatformTransactionManager beans bằng @Transactional(transactionManager=...) như thế nào?
Bạn phân biệt lựa chọn transaction manager bằng qualifier với việc đặt @Primary cho manager mặc định như thế nào?
Bạn sẽ cấu hình TransactionManagementConfigurer để chọn default manager theo yêu cầu nào?
Bạn đánh giá rủi ro một service sử dụng transaction manager của database A nhưng repository ghi vào database B ra sao?
Bạn sẽ xác minh manager được sử dụng thực tế khi một method @Transactional chạy như thế nào?
Bạn mô tả @EnableTransactionManagement kích hoạt transaction annotation infrastructure trong Spring ra sao?
Bạn phân biệt cơ chế auto-configuration transaction của Spring Boot với @EnableTransactionManagement thủ công như thế nào?
Bạn giải thích TransactionInterceptor mở và hoàn tất transaction xung quanh method invocation qua Spring AOP proxy như thế nào?
Bạn sẽ xác minh bean service thực sự được bọc bởi JDK dynamic proxy hay CGLIB proxy bằng cách nào?
Bạn phân tích ảnh hưởng của proxyTargetClass tới việc inject service theo interface và implementation class như thế nào?
Bạn sẽ đánh giá khả năng intercept method private, final hoặc có visibility khác nhau theo proxy type và phiên bản Spring ra sao?
Bạn phân biệt mode AdviceMode.PROXY với AspectJ weaving khi cần intercept self-invocation như thế nào?
Bạn giải thích vì sao this.saveDetail gọi từ cùng bean có thể bỏ qua @Transactional trên method saveDetail?
Bạn sẽ tách một method transaction đặc biệt sang bean riêng để cuộc gọi đi qua proxy như thế nào?
Bạn phân tích rủi ro sửa self-invocation bằng AopContext.currentProxy làm domain code phụ thuộc proxy infrastructure ra sao?
Bạn sẽ kiểm thử external invocation và self-invocation của cùng một method @Transactional để chứng minh khác biệt như thế nào?
Bạn phân biệt gọi method từ @PostConstruct với gọi qua proxy sau khi bean hoàn tất khởi tạo ra sao?
Bạn sẽ xác định vì sao đối tượng service được tạo bằng new không nhận được transactional advice của Spring ra sao?
Bạn phân tích tác động của việc đặt @Transactional trên interface so với concrete class trong các cơ chế proxy như thế nào?
Bạn sẽ tổ chức annotation ở class và method để method-level override transaction attributes rõ ràng ra sao?
Bạn phân biệt transaction advice và custom logging advice về thứ tự khi cả hai đều được gắn vào một method như thế nào?
Bạn sẽ xác minh advisor chain khi @Order của một aspect thay đổi vị trí transaction boundary như thế nào?
Bạn giải thích propagation REQUIRED hoạt động thế nào khi caller chưa có transaction và khi đã có transaction?
Bạn phân biệt logical transaction scope với physical transaction khi hai methods REQUIRED lồng nhau ra sao?
Bạn sẽ thiết kế một outer service REQUIRED gọi hai repository methods cùng tham gia một transaction như thế nào?
Bạn phân tích vì sao inner REQUIRED đánh dấu rollback-only có thể ảnh hưởng transaction của outer method ra sao?
Bạn sẽ chẩn đoán UnexpectedRollbackException khi outer method nuốt exception nhưng cố commit transaction như thế nào?
Bạn phân biệt UnexpectedRollbackException với exception đầu tiên gây ra rollback-only status như thế nào?
Bạn sẽ lựa chọn propagation REQUIRES_NEW khi cần lưu audit record độc lập dù transaction ngoài rollback ra sao?
Bạn mô tả cách Spring suspend transaction hiện có trước khi mở REQUIRES_NEW transaction như thế nào?
Bạn phân biệt rollback của outer REQUIRED với commit thành công của inner REQUIRES_NEW như thế nào?
Bạn phân tích vì sao nested REQUIRES_NEW có thể yêu cầu connection khác trong khi outer connection vẫn bị giữ ra sao?
Bạn sẽ xác định kích thước connection pool phù hợp khi nhiều requests đồng thời gọi REQUIRES_NEW ra sao?
Bạn sẽ kiểm thử inner REQUIRES_NEW commit dữ liệu thành công dù outer method phát sinh exception như thế nào?
Bạn phân tích rủi ro self-invocation khiến cấu hình REQUIRES_NEW không được thực hiện như dự kiến ra sao?
Bạn giải thích propagation NESTED dựa trên JDBC savepoint khác với REQUIRES_NEW như thế nào?
Bạn phân biệt NESTED và REQUIRED khi inner method cần rollback một phần nhưng outer vẫn có thể tiếp tục ra sao?
Bạn sẽ xác định transaction manager và database có hỗ trợ savepoint cần cho NESTED hay không ra sao?
Bạn phân tích giới hạn của NESTED với JpaTransactionManager và persistence context như thế nào?
Bạn sẽ dùng NESTED cho một bước import tùy chọn mà lỗi không được làm mất các bước trước theo cách nào?
Bạn phân biệt savepoint rollback với commit của một physical transaction độc lập trong thực tế như thế nào?
Bạn sẽ kiểm thử rollback tới savepoint không xóa dữ liệu đã ghi trước đó trong outer transaction như thế nào?
Bạn giải thích propagation SUPPORTS thực thi thế nào khi có và không có transaction của caller?
Bạn sẽ lựa chọn SUPPORTS cho method chỉ đọc theo bối cảnh nào?
Bạn phân biệt NOT_SUPPORTED với SUPPORTS khi caller đang có transaction như thế nào?
Bạn mô tả cách NOT_SUPPORTED suspend transaction của caller để chạy một đoạn code không có transaction ra sao?
Bạn phân tích rủi ro NOT_SUPPORTED đọc database trước khi dữ liệu outer transaction được commit như thế nào?
Bạn giải thích propagation MANDATORY có tác dụng gì khi method được gọi mà không có transaction?
Bạn sẽ áp dụng MANDATORY để bảo đảm một helper chỉ chạy bên trong business transaction như thế nào?
Bạn phân biệt NEVER với NOT_SUPPORTED khi một method được gọi từ transaction đang active ra sao?
Bạn sẽ dùng NEVER để chủ động phát hiện lời gọi sai kiến trúc giữa hai tầng service trong trường hợp nào?
Bạn phân tích nguy cơ chuyển propagation từ REQUIRED sang NEVER làm hỏng luồng nghiệp vụ đã có transaction như thế nào?
Bạn sẽ lựa chọn propagation theo yêu cầu lưu dấu, rollback và đọc dữ liệu thay vì áp dụng REQUIRES_NEW đại trà ra sao?
Bạn mô tả validateExistingTransactions có thể kiểm tra mâu thuẫn isolation hoặc readOnly khi join transaction như thế nào?
Bạn phân biệt thuộc tính isolation của inner REQUIRED với isolation của transaction đã được outer khởi tạo ra sao?
Bạn đánh giá khi nào cần xem lại cấu trúc service thay vì bổ sung nhiều propagation modes để vá lỗi ra sao?
Bạn giải thích ISOLATION_DEFAULT phụ thuộc cấu hình mặc định của database thay vì áp đặt một mức isolation như thế nào?
Bạn phân biệt READ_UNCOMMITTED với READ_COMMITTED trong khả năng quan sát uncommitted data ra sao?
Bạn mô tả dirty read phát sinh như thế nào giữa hai transaction đồng thời?
Bạn sẽ kiểm tra database có thực sự hỗ trợ READ_UNCOMMITTED hay tự nâng cấp isolation như thế nào?
Bạn phân biệt non-repeatable read với phantom read bằng một ví dụ transaction Spring như thế nào?
Bạn sẽ thiết kế test chứng minh hai lần đọc cùng row có thể trả giá trị khác nhau dưới READ_COMMITTED ra sao?
Bạn giải thích REPEATABLE_READ bảo vệ những trường hợp nào tùy MVCC hoặc locking của database như thế nào?
Bạn phân tích vì sao REPEATABLE_READ không nhất thiết bảo vệ một invariant dựa trên predicate của nhiều rows ra sao?
Bạn sẽ lựa chọn SERIALIZABLE cho thao tác nghiệp vụ nhạy cảm và dự đoán tác động tới concurrency như thế nào?
Bạn phân biệt lost update với write skew khi hai Spring requests cập nhật dữ liệu cùng lúc ra sao?
Bạn sẽ thiết kế test cho write skew ở database production để đánh giá mức isolation cần thiết như thế nào?
Bạn phân tích tác động của isolation cao lên deadlocks, retries và throughput của hệ thống ra sao?
Bạn sẽ dùng @Version optimistic locking khi nào thay vì chọn isolation cao cho mọi transaction?
Bạn phân biệt optimistic locking với pessimistic row locking về thời gian giữ locks như thế nào?
Bạn sẽ phối hợp database unique constraint và transaction để chống tạo hai bản ghi cùng khóa nghiệp vụ ra sao?
Bạn phân tích vì sao isolation level không thay thế việc thiết kế khóa chính, ràng buộc và query phù hợp ra sao?
Bạn sẽ xác định cách thực thi transaction read-only có consistent snapshot theo engine database cụ thể ra sao?
Bạn đánh giá tác động của transaction dài tới MVCC vacuum hoặc undo retention như thế nào?
Bạn phân biệt connection autocommit với thao tác được Spring điều khiển qua transaction manager ra sao?
Bạn sẽ kiểm tra isolation được yêu cầu bởi inner transaction thực sự có hiệu lực khi nó chỉ join existing transaction ra sao?
Bạn giải thích readOnly=true trong @Transactional là một hint và không luôn là lệnh cấm ghi bắt buộc như thế nào?
Bạn sẽ xác định readOnly tác động tới JPA flush mode và JDBC connection theo implementation như thế nào?
Bạn phân tích vì sao readOnly có thể vẫn cho phép ghi dữ liệu ở một database mà Spring không báo lỗi như thế nào?
Bạn sẽ lựa chọn transaction read-only cho một báo cáo dài khi vẫn phải quan tâm chi phí connection và snapshot ra sao?
Bạn giải thích timeout của @Transactional được transaction manager áp dụng như thế nào?
Bạn phân biệt transaction timeout với query timeout, connection acquire timeout và HTTP deadline ra sao?
Bạn sẽ xác định cách một statement đang chạy có bị ngắt khi transaction timeout hết theo driver thực tế như thế nào?
Bạn đánh giá rủi ro transaction timeout ngắn hơn thời gian xử lý hợp lệ của batch job ra sao?
Bạn sẽ cấu hình timeout khác nhau cho luồng thanh toán nhanh và tác vụ xử lý nhiều bản ghi bằng cách nào?
Bạn mô tả mặc định Spring rollback với RuntimeException hoặc Error nhưng không mặc định với checked exception như thế nào?
Bạn phân biệt rollbackFor và noRollbackFor khi một method phát sinh exception nghiệp vụ ra sao?
Bạn sẽ bổ sung rollbackFor cho checked exception bắt buộc làm hủy toàn bộ giao dịch như thế nào?
Bạn phân tích rủi ro rollbackFor=Exception.class khiến giao dịch rollback với cả những tình huống nghiệp vụ cần commit ra sao?
Bạn sẽ đặt noRollbackFor theo một exception chỉ mang tính cảnh báo nhưng dữ liệu cần được giữ lại trong trường hợp nào?
Bạn đánh giá cách Spring chọn rollback rule khi có nhiều rule trùng nhau theo quan hệ kế thừa exception như thế nào?
Bạn phân tích tác động của việc exception checked được wrapper chuyển thành unchecked trước khi đi qua TransactionInterceptor ra sao?
Bạn sẽ xác định vì sao bắt exception và trả về giá trị bình thường làm interceptor không tự rollback ra sao?
Bạn sẽ dùng TransactionAspectSupport.currentTransactionStatus().setRollbackOnly để chỉ định rollback thủ công trong điều kiện nào?
Bạn phân biệt đánh dấu rollback-only với việc hoàn thành rollback và giải phóng resource ngay lập tức như thế nào?
Bạn sẽ kiểm thử method setRollbackOnly rồi return bình thường vẫn không commit dữ liệu ra sao?
Bạn phân tích vì sao exception phát sinh sau khi transaction đã commit không thể quay ngược thay đổi ở database như thế nào?
Bạn sẽ lập chính sách retry riêng cho deadlock, optimistic conflict và lỗi vi phạm unique constraint như thế nào?
Bạn giải thích DataSourceTransactionManager gắn JDBC Connection với thread đang chạy transaction bằng cơ chế nào?
Bạn phân biệt DataSourceUtils.getConnection với mở Connection trực tiếp rồi tự close hoặc commit trong một service như thế nào?
Bạn sẽ dùng JdbcTemplate để nhiều SQL statements cùng tham gia Spring-managed transaction mà không truyền Connection thủ công ra sao?
Bạn mô tả vai trò của TransactionSynchronizationManager trong việc bind resources và quản lý synchronizations như thế nào?
Bạn phân biệt transaction synchronization active với một physical transaction thật sự tồn tại ở resource manager ra sao?
Bạn sẽ xác minh resource đang được bind vào thread khi cần debug nhiều DataSources như thế nào?
Bạn phân tích vì sao ThreadLocal transaction context không tự đi theo task sang thread khác ra sao?
Bạn sẽ thiết kế @Async job tự mở transaction ở worker thread mà không chia sẻ JDBC Connection của caller như thế nào?
Bạn mô tả TransactionAwareDataSourceProxy giúp một legacy component tham gia resource handling của Spring theo cách nào?
Bạn phân biệt TransactionAwareDataSourceProxy với LazyConnectionDataSourceProxy về trách nhiệm như thế nào?
Bạn sẽ dùng LazyConnectionDataSourceProxy khi cần trì hoãn việc lấy physical JDBC Connection theo điều kiện nào?
Bạn đánh giá rủi ro cấu hình chồng DataSource proxies khiến transaction manager và JdbcTemplate dùng khác connection như thế nào?
Bạn phân tích vì sao một transaction giữ connection trong lúc gọi remote HTTP API làm giảm pool capacity ra sao?
Bạn sẽ thiết kế cách chia transaction thành đoạn ngắn khi một workflow cần gọi dịch vụ bên ngoài như thế nào?
Bạn xác định cách cleanup ResultSet hoặc statement mà không làm đóng resource do Spring transaction quản lý ra sao?
Bạn giải thích TransactionSynchronization cung cấp các callbacks nào cho quá trình chuẩn bị, commit và hoàn tất transaction?
Bạn phân biệt beforeCommit, afterCommit và afterCompletion về thời điểm và mục đích như thế nào?
Bạn sẽ đăng ký TransactionSynchronization để cập nhật telemetry sau commit hoặc rollback theo cách nào?
Bạn phân tích vì sao afterCommit callback không phải một bước có thể rollback cùng transaction đã hoàn tất ra sao?
Bạn sẽ dùng REQUIRES_NEW cho một thao tác ghi mới phát sinh sau commit khi dữ liệu phải được lưu bền vững như thế nào?
Bạn đánh giá ảnh hưởng của thứ tự TransactionSynchronization callbacks khi nhiều resources cần cleanup ra sao?
Bạn giải thích @TransactionalEventListener gắn sự kiện Spring ApplicationEvent với transaction phase như thế nào?
Bạn phân biệt BEFORE_COMMIT, AFTER_COMMIT, AFTER_ROLLBACK và AFTER_COMPLETION của TransactionPhase ra sao?
Bạn sẽ chọn @TransactionalEventListener(AFTER_COMMIT) khi một listener chỉ được thực thi sau commit như thế nào?
Bạn phân tích vì sao @TransactionalEventListener với fallbackExecution=false không chạy nếu sự kiện được phát ngoài transaction ra sao?
Bạn sẽ quyết định khi nào bật fallbackExecution và đặt kỳ vọng gì nếu không có transaction ra sao?
Bạn phân biệt @EventListener thông thường với @TransactionalEventListener về thời điểm và bảo đảm xử lý như thế nào?
Bạn sẽ kiểm thử AFTER_COMMIT listener không chạy khi transaction bị rollback bằng cách nào?
Bạn đánh giá rủi ro phát message trong afterCommit khi process crash trước lúc gửi xong mà database đã commit ra sao?
Bạn sẽ chọn transactional outbox để thay thế một afterCommit callback không có khả năng tự phục hồi trong trường hợp nào?
Bạn giải thích TransactionTemplate triển khai programmatic transaction management qua callback như thế nào?
Bạn phân biệt TransactionTemplate với gọi PlatformTransactionManager.getTransaction và commit thủ công ra sao?
Bạn sẽ dùng TransactionCallback để trả giá trị từ một đoạn xử lý dữ liệu có transaction như thế nào?
Bạn phân biệt TransactionCallbackWithoutResult với TransactionCallback có return value như thế nào?
Bạn sẽ dùng TransactionStatus.setRollbackOnly trong TransactionTemplate.execute khi phát hiện một điều kiện nghiệp vụ ra sao?
Bạn phân tích vì sao nuốt exception trong TransactionTemplate callback có thể dẫn đến commit không mong muốn như thế nào?
Bạn sẽ cấu hình propagation, isolation, readOnly và timeout của TransactionTemplate theo một use case cụ thể ra sao?
Bạn đánh giá rủi ro tái sử dụng cùng TransactionTemplate với cấu hình cứng cho nhiều luồng nghiệp vụ khác nhau như thế nào?
Bạn sẽ phân biệt TransactionTemplate.execute gọi bên trong method @Transactional REQUIRED với một transaction hoàn toàn độc lập như thế nào?
Bạn sẽ chọn TransactionTemplate khi một method có nhiều đoạn code chỉ một đoạn cần giao dịch theo tiêu chí nào?
Bạn phân tích vì sao lồng TransactionTemplate với REQUIRES_NEW hoặc NESTED cần xét manager và physical connection ra sao?
Bạn sẽ kiểm thử TransactionTemplate callback phát sinh exception và resource được rollback như thế nào?
Bạn giải thích vì sao EntityManager.flush không đồng nghĩa với database commit trong JPA transaction như thế nào?
Bạn phân biệt dirty checking của JpaTransactionManager/JPA context với hành vi update trực tiếp của JdbcTemplate ra sao?
Bạn sẽ chọn flush sớm khi muốn phát hiện constraint violation trước một bước side effect như thế nào?
Bạn đánh giá rủi ro lazy-loading dữ liệu sau khi persistence context hoặc transaction đóng như thế nào?
Bạn sẽ phân tích OpenEntityManagerInView có thể che một ranh giới transaction thiết kế thiếu rõ ràng ra sao?
Bạn phân biệt EntityManager.clear với rollback của database transaction như thế nào?
Bạn sẽ xử lý optimistic lock conflict bằng @Version khi hai requests sửa cùng một entity như thế nào?
Bạn giải thích JtaTransactionManager phối hợp nhiều XA resources bằng transaction coordinator theo cơ chế nào?
Bạn phân biệt two-phase commit với một saga có compensating actions theo khả năng bảo đảm và chi phí vận hành ra sao?
Bạn sẽ đánh giá trạng thái in-doubt sau khi coordinator mất kết nối trong distributed transaction như thế nào?
Bạn phân tích vì sao XA không tự ngăn việc HTTP caller gửi lại cùng business request sau timeout ra sao?
Bạn giải thích ReactiveTransactionManager liên kết transaction với Reactor Context thay vì ThreadLocal như thế nào?
Bạn phân biệt R2dbcTransactionManager với DataSourceTransactionManager khi cùng dùng Spring transaction abstractions ra sao?
Bạn sẽ dùng TransactionalOperator để bao quanh một Mono hoặc Flux chain trong một reactive transaction như thế nào?
Bạn mô tả transaction reactive được bắt đầu tại subscription của publisher theo cơ chế nào?
Bạn sẽ thiết kế @Transactional method trả Mono sao cho mọi database operations đều nằm trong cùng publisher ra sao?
Bạn phân tích vì sao tự gọi subscribe trong service khiến thao tác có thể thoát khỏi reactive transaction context như thế nào?
Bạn phân biệt lỗi đồng bộ khi tạo Mono với error signal phát sinh khi thực thi SQL trong transaction như thế nào?
Bạn sẽ đặt onErrorResume ở đâu để lỗi khiến transaction rollback trước khi chuyển thành HTTP response hợp lệ ra sao?
Bạn đánh giá rủi ro onErrorResume bên trong transaction nuốt lỗi khiến database được commit ngoài mong đợi như thế nào?
Bạn phân tích cách subscriber cancellation ảnh hưởng rollback, commit và cleanup của một reactive transaction như thế nào?
Bạn sẽ kiểm tra cancellation một Flux dài có giải phóng connection và transaction resources như thế nào?
Bạn đánh giá rủi ro flatMap gửi nhiều SQL queries đồng thời trên một connection đang dùng chung transaction ra sao?
Bạn sẽ dùng concatMap hoặc then để bảo đảm thứ tự của những bước ghi dữ liệu trong reactive transaction như thế nào?
Bạn phân biệt timeout do Reactor với transaction timeout và statement timeout trên R2DBC driver ra sao?
Bạn sẽ thiết kế @Transactional reactive service không giữ transaction mở đến khi browser tiêu thụ hết response stream ra sao?
Bạn phân tích vì sao JDBC blocking operation không tự được gộp vào transaction của một R2dbcTransactionManager ra sao?
Bạn sẽ dùng StepVerifier để xác minh commit trên onComplete và rollback trên onError của transactional publisher như thế nào?
Bạn đánh giá khi nào nên giữ giao dịch JDBC imperative thay vì chuyển sang reactive khi hệ thống còn nhiều thư viện blocking ra sao?
Bạn giải thích vì sao transaction context từ caller không tự đi qua @Async sang worker thread như thế nào?
Bạn sẽ tạo transaction mới trong worker khi một @Async method thực thi ghi database theo cách nào?
Bạn phân tích hậu quả của việc truyền JDBC Connection hoặc EntityManager của caller sang asynchronous callback như thế nào?
Bạn sẽ quyết định khi nào một CompletableFuture error xảy ra quá muộn để rollback giao dịch của method gọi ra sao?
Bạn đánh giá khác biệt giữa CompletableFuture đã failed trước khi method return và lỗi được ghi nhận về sau đối với Spring transaction advice ra sao?
Bạn sẽ cấu hình thứ tự @Retryable và @Transactional để mỗi attempt có transaction riêng khi xảy ra transient failure như thế nào?
Bạn phân tích vì sao retry ngay trong transaction đã rollback-only sẽ không cứu được transaction như thế nào?
Bạn sẽ cân nhắc @Cacheable và @Transactional cùng một method khi cache hit bỏ qua target execution như thế nào?
Bạn sẽ trì hoãn cache invalidation tới sau commit khi cần tránh phát trạng thái chưa bền vững bằng cách nào?
Bạn phân tích vì sao chạy nghiệp vụ từ listener @TransactionalEventListener bằng @Async cần mở transaction riêng như thế nào?
Bạn sẽ thiết kế logic gửi thông báo tránh giữ row locks trong lúc gọi một API bên ngoài ra sao?
Bạn sẽ đánh giá ranh giới transaction cho từng chunk khi xử lý batch hàng triệu rows như thế nào?
Bạn phân biệt retry một chunk đã rollback với retry cả job khi thiết kế idempotent batch processing ra sao?
Bạn giải thích Spring TestContext quản lý rollback mặc định cho integration test method đánh dấu @Transactional như thế nào?
Bạn sẽ kiểm tra @Transactional service được Spring proxy thực sự advice thay vì dùng new Service trong unit test ra sao?
Bạn phân biệt test transaction của Spring TestContext với transaction thật của service gọi qua HTTP vào thread khác như thế nào?
Bạn sẽ sử dụng @Rollback(false) hoặc @Commit khi test cần xác minh commit-time behavior như thế nào?
Bạn phân biệt @BeforeTransaction và @AfterTransaction theo thời điểm chúng chạy so với transaction test ra sao?
Bạn đánh giá rủi ro @Transactional test rollback mặc định làm bỏ sót lỗi xảy ra chỉ lúc commit như thế nào?
Bạn sẽ dùng EntityManager.flush hoặc JdbcTemplate query để kiểm chứng constraint violation thực tế trong integration test ra sao?
Bạn phân tích vì sao service gọi REQUIRES_NEW có thể commit dữ liệu dù test transaction bên ngoài cuối cùng rollback ra sao?
Bạn sẽ thiết kế kiểm thử REQUIRED tham gia transaction đã có và REQUIRES_NEW thực hiện commit độc lập như thế nào?
Bạn sẽ kiểm tra NESTED rollback về savepoint đúng như kỳ vọng trên database thực tế bằng test nào?
Bạn đánh giá khi nào nên dùng Testcontainers thay vì database in-memory để kiểm tra isolation và savepoint support ra sao?
Bạn sẽ tạo hai threads với hai transactions đồng thời để tái hiện lost update hoặc phantom read theo cách nào?
Bạn phân tích cách kiểm thử @Version ngăn cập nhật mất dữ liệu khi nhiều requests tranh chấp cùng row ra sao?
Bạn sẽ kiểm tra checked exception không rollback mặc định và có rollback khi cấu hình rollbackFor như thế nào?
Bạn đánh giá cách test TransactionSynchronization.afterCompletion nhận đúng committed hoặc rolled-back status ra sao?
Bạn sẽ kiểm thử @TransactionalEventListener(AFTER_COMMIT) không phát event khi transaction bị rollback ra sao?
Bạn sẽ dùng TransactionTemplate trong test để tạo hai transaction độc lập và quan sát committed data như thế nào?
Bạn phân tích vì sao test chạy transaction trong thread test không bảo đảm một WebFlux controller async dùng cùng transaction như thế nào?
Bạn sẽ dùng AopUtils.isAopProxy để xác minh proxy cấu hình transaction đang tồn tại trong ApplicationContext như thế nào?
Bạn sẽ thiết kế stress test timeout và deadlock ổn định, có giới hạn và làm sạch dữ liệu sau mỗi lần chạy ra sao?
Bạn mô tả cách dùng Micrometer và Spring Boot Actuator để quan sát pool wait, transaction duration và rollback rate như thế nào?
Bạn sẽ phân biệt lỗi deadlock, lock timeout, optimistic conflict và UnexpectedRollbackException trong runbook ra sao?
Bạn sẽ giới hạn metric labels để tránh đưa ID người dùng hoặc transaction ID làm tăng cardinality ra sao?
Bạn sẽ thu thập trace và log transaction failure mà không lộ SQL parameters nhạy cảm như thế nào?
Bạn đánh giá khi nào pool saturation do REQUIRES_NEW lồng nhau tạo p99 latency tăng mặc dù CPU thấp ra sao?
Bạn sẽ xác định nguyên nhân long-running transaction từ database lock metrics và application traces như thế nào?
Bạn phân tích vì sao tăng timeout không giải quyết gốc rễ của deadlock hoặc query thiếu index như thế nào?
Bạn sẽ thiết kế backoff khi database failover để tránh nhiều services retry transaction đồng loạt như thế nào?
Bạn đánh giá rủi ro schema migration trong rolling deployment làm old và new service transactions sử dụng constraints khác nhau ra sao?
Bạn sẽ đặt tài khoản database chạy application với least privilege nhưng vẫn thực hiện được các transactions cần thiết như thế nào?
Nếu inner REQUIRED đánh dấu rollback-only nhưng outer đã nuốt exception, bạn sẽ khoanh vùng UnexpectedRollbackException và sửa thế nào?
Nếu self-invocation khiến REQUIRES_NEW không mở transaction mới, bạn sẽ refactor bean và kiểm thử ra sao?
Nếu NESTED không dùng được với JpaTransactionManager hiện tại, bạn sẽ đánh giá savepoint support và phương án khác như thế nào?
Nếu connection pool cạn khi tải tăng do nested REQUIRES_NEW, bạn sẽ thay đổi propagation hoặc capacity planning ra sao?
Nếu checked exception không rollback, bạn sẽ kiểm tra rollbackFor và proxy call path như thế nào?
Nếu @Transactional(readOnly=true) vẫn cho phép ghi dữ liệu, bạn sẽ bổ sung bảo vệ hoặc điều chỉnh kỳ vọng ra sao?
Nếu một READ_COMMITTED transaction đọc hai lần có kết quả khác nhau, bạn sẽ kiểm tra isolation và giao dịch concurrent ra sao?
Nếu SERIALIZABLE transaction bị serialization failure trong tải cao, bạn sẽ thiết kế retry và idempotency ra sao?
Nếu transaction timeout đã hết nhưng JDBC statement vẫn chờ lock, bạn sẽ điều chỉnh statement timeout và lock timeout thế nào?
Nếu một legacy DAO tự mở connection ngoài DataSourceUtils và commit, bạn sẽ sửa resource management ra sao?
Nếu database commit nhưng JMS publish sau commit bị mất do process crash, bạn sẽ chọn outbox thay cho callback như thế nào?
Nếu @TransactionalEventListener(AFTER_COMMIT) ghi database nhưng kết quả không được commit riêng, bạn sẽ tổ chức REQUIRES_NEW ra sao?
Nếu TransactionTemplate callback gọi setRollbackOnly mà vẫn trả kết quả thành công, bạn sẽ xác minh dữ liệu ở database như thế nào?
Nếu @Async listener không nhìn thấy dữ liệu chưa commit của caller, bạn sẽ điều chỉnh event phase hoặc orchestration ra sao?
Nếu R2DBC pipeline tự subscribe làm thay đổi transaction boundary, bạn sẽ compose publisher để giữ Reactor Context như thế nào?
Nếu onErrorResume làm một reactive transaction commit sau error, bạn sẽ chuyển chỗ xử lý lỗi để rollback đúng như thế nào?
Nếu test @Transactional luôn xanh nhưng production lỗi ở commit, bạn sẽ thêm bước flush, commit và integration assertions ra sao?
Nếu client retry sau HTTP timeout trong khi transaction trước có thể đã commit, bạn sẽ kết hợp idempotency key và unique constraint như thế nào?
Nếu cần thiết kế giao dịch trong một ứng dụng Spring nhiều module, bạn sẽ chọn transaction manager, propagation, isolation, rollback policy, synchronization và kiểm thử như thế nào?
