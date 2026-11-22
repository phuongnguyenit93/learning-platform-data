# Method parameter names và metadata phục vụ expression trong Spring

Một số tính năng của Spring cho phép viết SpEL expression ngay trên method annotation. Ví dụ, cache annotation có thể dùng tham số của method để tạo cache key, còn method security có thể kiểm tra tham số trước khi cho phép gọi method:

~~~java
@Cacheable(cacheNames = "books", key = "#isbn")
public Book findBook(ISBN isbn) {
    // ...
}

@PreAuthorize("#owner == authentication.name")
public Account getAccount(String owner) {
    // ...
}
~~~

Trong các ví dụ này, #isbn và #owner là tên tham số của method. SpEL không tự suy ra tên đó chỉ từ chuỗi expression. Spring cần metadata của method và một cơ chế khám phá tên tham số (ParameterNameDiscoverer) để đưa các tham số vào EvaluationContext.

Khi tên tham số không có sẵn, nhiều integration của Spring còn cung cấp biến theo vị trí như #p0 hoặc #a0. Cú pháp và các biến được hỗ trợ phụ thuộc vào tính năng annotation đang đánh giá expression; không phải mọi annotation Spring đều cung cấp cùng một evaluation context.

## 1. Vì sao expression cần metadata của method?

Một method Java có thể khai báo:

~~~java
public Book findBook(ISBN isbn, boolean includeReviews) {
    // ...
}
~~~

Khi framework đánh giá expression gắn với method invocation, nó cần biết:

- Method nào đang được gọi.
- Đối tượng target nào nhận lời gọi.
- Các đối số runtime và thứ tự của chúng.
- Tên, kiểu và annotation của từng tham số nếu cần.
- Kiểu trả về và metadata liên quan đến method.
- Ngữ cảnh của annotation hoặc interceptor đang xử lý lời gọi.

Metadata này giúp Spring liên kết expression với đúng dữ liệu của lần gọi hiện tại. Ví dụ, #isbn có thể được gán từ đối số đầu tiên của findBook, còn #includeReviews lấy từ đối số thứ hai nếu tên tham số được khám phá thành công.

Nếu framework không lấy được tên tham số, expression vẫn có thể được parse, nhưng biến có tên đó có thể không được đưa vào context. Khi đó cần dùng alias theo vị trí hoặc cấu hình metadata phù hợp.

## 2. Tên tham số Java không phải lúc nào cũng có trong bytecode

Trong mã nguồn, tên tham số luôn xuất hiện:

~~~java
public Account getAccount(String owner, Long tenantId) {
    // ...
}
~~~

Tuy nhiên, tên owner và tenantId không nhất thiết được lưu trong file .class theo cách reflection có thể đọc. Java compiler có thể bỏ tên tham số nếu không được yêu cầu giữ metadata.

Để reflection đọc được tên tham số, biên dịch Java với tùy chọn:

~~~text
-parameters
~~~

Ví dụ với javac:

~~~bash
javac -parameters -d out src/main/java/com/example/AccountService.java
~~~

Khi class được biên dịch với metadata này, Java reflection có thể đọc tên qua Parameter:

~~~java
Method method =
    AccountService.class.getMethod(
        "getAccount",
        String.class,
        Long.class
    );

for (Parameter parameter : method.getParameters()) {
    System.out.println(parameter.getName());
    System.out.println(parameter.isNamePresent());
}
~~~

Nếu metadata tên tham số được lưu, isNamePresent() trả về true và getName() trả về tên như owner hoặc tenantId.

Nếu không có metadata, reflection có thể trả về tên tổng hợp như arg0, arg1 và isNamePresent() là false. Những tên này không phải tên tham số nghiệp vụ trong source code.

## 3. Cấu hình compiler để giữ tên tham số

Với Maven Compiler Plugin, có thể bật tùy chọn parameters:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <configuration>
        <parameters>true</parameters>
    </configuration>
</plugin>
~~~

Với Gradle Java plugin:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ['-parameters']
}
~~~

Sau khi thay đổi cấu hình, cần biên dịch lại các class có method được expression sử dụng. Chỉ sửa build file nhưng tiếp tục chạy bytecode cũ sẽ không bổ sung metadata vào những class đã biên dịch trước đó.

Với dự án nhiều module, cần bật tùy chọn ở module thực sự biên dịch class chứa method được gọi. Nếu method nằm trong thư viện bên ngoài, metadata phải có sẵn trong artifact của thư viện đó hoặc integration phải dùng cơ chế đặt tên khác.

## 4. ParameterNameDiscoverer làm nhiệm vụ gì?

Spring Core cung cấp abstraction ParameterNameDiscoverer để khám phá tên tham số từ method hoặc constructor.

Một implementation phổ biến là StandardReflectionParameterNameDiscoverer. Nó sử dụng Java reflection và cần metadata tên tham số được lưu trong bytecode, thường thông qua javac -parameters.

DefaultParameterNameDiscoverer là lựa chọn tổng hợp mà Spring cung cấp cho nhiều trường hợp. Nó có thể kết hợp cơ chế phù hợp với môi trường, chẳng hạn hỗ trợ metadata Kotlin khi có mặt và reflection parameter metadata của Java.

Các integration khác có thể dùng discoverer riêng hoặc bổ sung chiến lược đọc annotation đặt tên tham số. Vì vậy, cần kiểm tra tài liệu của tính năng đang dùng để biết chính xác nguồn metadata được hỗ trợ.

Không nên giả định mọi phiên bản Spring đều suy ra tên tham số từ debug local-variable table theo cùng một cách. Với Java hiện đại, biên dịch bằng -parameters là cách rõ ràng và ổn định để cung cấp tên cho reflection.

## 5. MethodParameter và metadata của từng tham số

Spring Core có lớp MethodParameter để mô tả một tham số cụ thể của method hoặc constructor.

MethodParameter có thể cung cấp thông tin như:

- Method hoặc constructor chứa tham số.
- Vị trí tham số (parameter index).
- Kiểu Java của tham số.
- Generic type khi có thể xác định.
- Annotation trên tham số.
- Tên tham số thông qua cơ chế khám phá tên phù hợp.

Ví dụ, method:

~~~java
public void update(
        @NotNull String accountId,
        @Valid UpdateRequest request) {
    // ...
}
~~~

có hai tham số ở index 0 và 1. Metadata có thể giúp framework biết kiểu của từng tham số và các annotation gắn với chúng.

Metadata này không chỉ phục vụ SpEL. Spring còn dùng thông tin method và parameter trong data binding, validation, argument resolution, dependency injection và nhiều cơ chế AOP khác.

## 6. Tên tham số trong annotation expression phụ thuộc integration

SpEL là ngôn ngữ biểu thức chung. Nhưng việc một annotation cung cấp những biến nào là trách nhiệm của tính năng Spring xử lý annotation đó.

Ví dụ:

- Spring Cache tạo context có thông tin về method, target, arguments và cache.
- Spring Security method authorization tạo context có authentication, principal và thông tin method invocation.
- Spring Data có thể dùng parameter metadata trong query expression theo quy ước riêng.
- @Value thường đánh giá expression trong môi trường bean/configuration và không tự động có các method arguments như cache hoặc method security.

Vì vậy, không nên lấy danh sách biến của @Cacheable rồi mặc định rằng @Value hoặc mọi annotation khác cũng cung cấp các biến đó.

Khi viết expression cho annotation, hãy xác định annotation thuộc module nào, tài liệu của module đó mô tả evaluation root và variables ra sao, rồi mới chọn tên biến.

## 7. Biến theo vị trí: #p0 và #a0

Nhiều method-based evaluation context của Spring cung cấp alias theo vị trí cho các đối số:

- #p0: tham số ở vị trí 0.
- #a0: tham số ở vị trí 0.
- #p1 và #a1: tham số ở vị trí 1.
- Các vị trí tiếp theo tăng dần từ 0.

Ví dụ:

~~~java
@Cacheable(cacheNames = "books", key = "#p0")
public Book findBook(ISBN isbn) {
    // ...
}
~~~

Expression dùng đối số đầu tiên mà không cần biết tên tham số trong bytecode.

Với method có hai tham số:

~~~java
@Cacheable(
    cacheNames = "books",
    key = "#p0 + ':' + #p1"
)
public Book findBook(ISBN isbn, String language) {
    // ...
}
~~~

#p0 đại diện isbn và #p1 đại diện language theo thứ tự khai báo.

Các alias này được framework đưa vào context; chúng không phải cú pháp đặc biệt mà SpEL tự tạo cho mọi method trong mọi loại context. Hãy kiểm tra tính năng annotation đang dùng có cung cấp chúng hay không.

## 8. #root.args và metadata root trong Spring Cache

Spring Cache cung cấp một evaluation context chuyên biệt cho các expression trong cache annotation. Root object của context này có các thuộc tính hữu ích như:

| Thuộc tính | Ý nghĩa |
|---|---|
| #root.method | Method đang được gọi |
| #root.methodName | Tên method |
| #root.target | Object target |
| #root.targetClass | Kiểu của target |
| #root.args | Mảng các đối số method |
| #root.caches | Các Cache đang được dùng |

Ví dụ:

~~~java
@Cacheable(
    cacheNames = "books",
    key = "#root.methodName + ':' + #root.args[0]"
)
public Book findBook(ISBN isbn) {
    // ...
}
~~~

Expression tạo key từ tên method và đối số đầu tiên.

Có thể dùng #root.args[0] khi muốn thể hiện rõ việc truy cập đối số theo index. #p0 và #a0 thường ngắn gọn hơn khi integration cung cấp các alias đó.

Root object và metadata của cache là quy ước của Spring Cache. Không nên mặc định root của một annotation khác có cùng các property này.

## 9. Ví dụ với @Cacheable: tên tham số và fallback theo index

~~~java
@Service
public class BookService {

    @Cacheable(cacheNames = "books", key = "#isbn")
    public Book findBook(ISBN isbn) {
        return loadBook(isbn);
    }
}
~~~

Nếu tên isbn được khám phá thành công, expression có thể dùng #isbn.

Khi build không lưu tên tham số hoặc integration không thể khám phá tên đó, có thể dùng alias vị trí mà Spring Cache hỗ trợ:

~~~java
@Cacheable(cacheNames = "books", key = "#p0")
public Book findBook(ISBN isbn) {
    return loadBook(isbn);
}
~~~

Hoặc dùng root metadata:

~~~java
@Cacheable(cacheNames = "books", key = "#root.args[0]")
public Book findBook(ISBN isbn) {
    return loadBook(isbn);
}
~~~

Cả ba cách đều hướng tới đối số đầu tiên, nhưng tên tham số dễ đọc hơn khi metadata ổn định. Alias theo index không phụ thuộc tên source code, đổi lại expression phải được cập nhật nếu thứ tự tham số thay đổi.

## 10. Ví dụ với method security

Spring Security hỗ trợ SpEL trong các annotation method authorization như @PreAuthorize và @PostAuthorize.

Ví dụ:

~~~java
@PreAuthorize("#owner == authentication.name")
public Account getAccount(String owner) {
    // ...
}
~~~

Expression so sánh owner với tên principal đang xác thực. Việc dùng #owner phụ thuộc cơ chế khám phá tên tham số của Spring Security và metadata có sẵn.

Có thể dùng index alias khi phù hợp với context của Spring Security:

~~~java
@PreAuthorize("#p0 == authentication.name")
public Account getAccount(String owner) {
    // ...
}
~~~

Spring Security cũng hỗ trợ annotation đặt tên tham số riêng, chẳng hạn @P, trong những trường hợp cần cung cấp tên tường minh:

~~~java
@PreAuthorize("#userId == authentication.name")
public Account getAccount(@P("userId") String owner) {
    // ...
}
~~~

@P thuộc Spring Security. Đây không phải annotation chung mà mọi Spring expression integration đều tự động hiểu. Hãy dùng đúng annotation mà module đang sử dụng hỗ trợ.

## 11. Annotation đặt tên tham số tường minh

Một số module Spring hỗ trợ annotation để khai báo tên tham số mà không phụ thuộc hoàn toàn vào compiler metadata.

Ví dụ, Spring Security cung cấp @P:

~~~java
public Account getAccount(@P("userId") String owner) {
    // ...
}
~~~

Spring Data có annotation @Param trong các API query tương ứng:

~~~java
@Query("select u from User u where u.email = :email")
User findByEmail(@Param("email") String address);
~~~

Các annotation này thuộc những integration cụ thể. Tên annotation, package và cách expression/query sử dụng metadata cần tuân theo module tương ứng.

Nếu một tính năng hỗ trợ annotation đặt tên tham số, đây là cách tường minh để khai báo tên mà expression hoặc query cần dùng. Nếu không hỗ trợ, chỉ thêm annotation cùng tên ở module khác sẽ không tự làm cho ParameterNameDiscoverer nhận ra nó.

## 12. Method parameter metadata và proxy/AOP

Nhiều annotation được thực thi thông qua proxy hoặc interceptor. Framework có thể nhận được method từ interface, method triển khai hoặc method đã được phân giải qua proxy.

Điều này có thể ảnh hưởng đến việc tìm metadata, đặc biệt khi:

- Interface và implementation đặt tên tham số khác nhau.
- Method được kế thừa từ lớp cha.
- Compiler tạo bridge method do generic hoặc override.
- Proxy gọi method thông qua interface.
- Artifact runtime khác với source code đang mở trong IDE.

Khi tên tham số không được tìm thấy như mong đợi, hãy kiểm tra method thực tế mà interceptor xử lý và bytecode của class đang chạy. Bật -parameters cho module implementation là lựa chọn tốt; nếu framework hỗ trợ annotation tên tham số, hãy dùng annotation đúng vị trí và đúng loại method.

## 13. Kiểm tra metadata tên tham số bằng Java reflection

Có thể kiểm tra trực tiếp bytecode mà JVM đang nạp:

~~~java
Method method =
    BookService.class.getMethod(
        "findBook",
        ISBN.class
    );

Parameter parameter =
    method.getParameters()[0];

System.out.println(parameter.getName());
System.out.println(parameter.isNamePresent());
~~~

Nếu isNamePresent() là true, tên tham số được lưu và reflection có thể đọc. Nếu false, tên như arg0 không phải bằng chứng rằng source code đã khai báo tham số tên arg0; đó có thể chỉ là tên tổng hợp do reflection cung cấp.

Đây là bước chẩn đoán hữu ích khi expression không nhận được #isbn như dự kiến. Nó kiểm tra metadata của class runtime, không kiểm tra trực tiếp mọi ParameterNameDiscoverer mà một module cụ thể đang sử dụng.

## 14. Phân biệt lỗi parsing và lỗi parameter resolution

Expression có thể được phân tích thành công dù biến tên tham số không được cung cấp khi evaluation.

Ví dụ:

~~~spel
#owner == authentication.name
~~~

Parser hiểu cú pháp #owner. Nhưng khi framework đánh giá, nếu không có biến owner trong EvaluationContext thì kết quả có thể không như mong đợi hoặc phần truy cập tiếp theo có thể phát sinh lỗi.

Do đó, cần tách hai giai đoạn:

- **Parsing:** cú pháp SpEL có hợp lệ không?
- **Evaluation context construction:** framework có đưa đúng method arguments và tên biến vào context không?
- **Evaluation:** expression có đọc được biến, root property và authentication data không?

Nếu expression parse được nhưng #owner không có giá trị, việc sửa cú pháp không giải quyết được vấn đề metadata. Hãy kiểm tra compiler flags, parameter-name discovery và quy ước của annotation integration.

## 15. Đặt tên và thứ tự tham số để expression dễ bảo trì

Expression gắn với annotation thường tồn tại lâu cùng method signature. Một số nguyên tắc giúp giảm lỗi:

- Dùng tên tham số có ý nghĩa nghiệp vụ, tránh tên chung chung như x hoặc value nếu có nhiều tham số.
- Bật -parameters nhất quán trong module Java cần metadata.
- Dùng alias #p0 hoặc #a0 khi muốn tránh phụ thuộc tên, nhưng ghi nhớ thứ tự tham số là một phần của expression contract.
- Với module hỗ trợ annotation tên tham số, cân nhắc dùng annotation khi build metadata không thể được bảo đảm.
- Khi đổi thứ tự hoặc kiểu tham số, kiểm tra lại mọi annotation expression tham chiếu theo index.
- Giữ expression ngắn và chỉ tham chiếu những tham số thực sự cần thiết.

Nếu một expression phải truy cập nhiều tham số, có thể cân nhắc gom dữ liệu nghiệp vụ vào một object có cấu trúc rõ ràng nếu API và annotation integration cho phép.

## 16. Những nhầm lẫn thường gặp

**Nhầm lẫn 1: Tên tham số trong source luôn có sẵn ở runtime.**  
Tên có thể không được lưu trong bytecode. Dùng -parameters hoặc cơ chế annotation mà integration hỗ trợ.

**Nhầm lẫn 2: #p0 và #a0 là biến toàn cục của mọi SpEL context.**  
Đây là alias thường được method-based integration đưa vào context. Khả năng dùng phụ thuộc annotation/module cụ thể.

**Nhầm lẫn 3: Mọi annotation Spring đều có cùng root object và method arguments.**  
Mỗi integration định nghĩa evaluation context riêng. Một annotation thậm chí có thể không hỗ trợ SpEL.

**Nhầm lẫn 4: Thêm @P hoặc @Param ở bất kỳ đâu cũng làm tên tham số hoạt động.**  
Chỉ integration có ParameterNameDiscoverer hỗ trợ annotation đó mới sử dụng metadata tương ứng.

**Nhầm lẫn 5: Expression parse thành công nghĩa là tên tham số đã được giải quyết.**  
Tên biến được cung cấp khi xây dựng EvaluationContext và được tra cứu trong lúc evaluation.

**Nhầm lẫn 6: Đổi tên tham số Java không bao giờ ảnh hưởng expression.**  
Nếu expression dùng tên tham số, đổi tên có thể làm mất biến tương ứng. Alias theo index tránh phụ thuộc tên nhưng vẫn phụ thuộc thứ tự.

## 17. Ghi nhớ

- Spring cần method metadata và cơ chế ParameterNameDiscoverer để cung cấp tên tham số cho annotation expression.
- Java reflection đọc tên tham số ổn định khi class được biên dịch với -parameters.
- DefaultParameterNameDiscoverer và các discoverer riêng của module có thể kết hợp nhiều nguồn metadata.
- MethodParameter mô tả method, index, kiểu và annotation của tham số.
- Nhiều method-based context cung cấp alias theo vị trí như #p0 và #a0; cần xác nhận alias theo annotation integration.
- Spring Cache có root metadata như #root.method, #root.methodName, #root.target, #root.args và #root.caches.
- Spring Security method expressions có context riêng, có thể cung cấp authentication và hỗ trợ tên tham số theo quy tắc của module.
- Annotation như @P của Spring Security hoặc @Param của Spring Data chỉ có tác dụng trong integration tương ứng.
- #name là biến được framework đưa vào EvaluationContext; nó không tự động được SpEL suy ra từ source code.
- Khi debug, kiểm tra bytecode runtime, compiler option, method thực tế sau proxy và context mà annotation tạo ra.

Khi viết SpEL cho method annotation, hãy xác định rõ integration đang dùng, kiểm tra những biến và root metadata mà integration cung cấp, bật -parameters cho class liên quan hoặc dùng annotation tên tham số được hỗ trợ, rồi chọn tên biến hay alias theo index phù hợp với hợp đồng của method.
