# SpEL trong XML bean definition

## Mục tiêu

Spring Expression Language (SpEL) có thể được dùng trong các giá trị của XML bean definition. Khi một giá trị bắt đầu bằng delimiter **#{** và kết thúc bằng **}**, Spring đánh giá phần bên trong như một expression rồi dùng kết quả để cấu hình property, constructor argument hoặc phần tử collection trong quá trình tạo bean.

Cách này hữu ích khi cấu hình cần một phép tính, đọc system property, tham chiếu một bean khác hoặc kết hợp nhiều giá trị mà không phải viết một bean factory riêng. Tuy nhiên, cần phân biệt expression của SpEL với property placeholder, hiểu thời điểm expression được đánh giá và tuân thủ quy tắc escape của XML.

Sau bài này, bạn có thể:

- Dùng #{...} trong XML bean definition.
- Đặt SpEL expression trong property value và constructor argument.
- Tham chiếu system properties, static members và Spring beans.
- Dùng expression trong list, set, map và các giá trị lồng nhau.
- Phân biệt SpEL expression với property placeholder.
- Escape ký tự đặc biệt theo cú pháp XML.
- Hiểu thời điểm expression được đánh giá trong vòng đời bean.
- Chẩn đoán lỗi parse, resolve bean, conversion và XML parsing.

## 1. Cú pháp SpEL trong XML

Trong XML bean definition, SpEL expression thường được đặt trong dấu phân cách **#{** và **}**:

~~~xml
<bean id="welcomeMessage" class="com.example.WelcomeMessage">
    <property name="text" value="#{'Hello from SpEL'}"/>
</bean>
~~~

Spring nhận diện chuỗi có expression delimiter trong giá trị bean definition, đánh giá phần SpEL và gán kết quả cho property text.

Một ví dụ dùng system property:

~~~xml
<bean id="applicationRegion" class="com.example.RegionSettings">
    <property name="region"
              value="#{systemProperties['user.region']}"/>
</bean>
~~~

Expression đọc entry user.region từ system properties. Kết quả được chuyển đổi sang kiểu property nếu conversion phù hợp được cấu hình.

Không phải mọi chuỗi XML đều tự động trở thành SpEL. Phần văn bản cần được đánh giá phải dùng delimiter expression và được Spring xử lý trong một ApplicationContext có bean expression resolver.

## 2. Dùng expression trong property value

Một trong những cách sử dụng phổ biến nhất là tính giá trị property khi bean được tạo.

~~~xml
<bean id="pricingSettings" class="com.example.PricingSettings">
    <property name="maximumPrice"
              value="#{T(java.math.BigDecimal).valueOf(500)}"/>
    <property name="defaultCurrency"
              value="#{T(java.util.Currency).getInstance('USD')}"/>
</bean>
~~~

Expression đầu tiên gọi static method valueOf của BigDecimal. Expression thứ hai lấy Currency tương ứng với mã USD.

Có thể tham chiếu property hoặc method của một bean khác:

~~~xml
<bean id="checkoutSettings" class="com.example.CheckoutSettings">
    <property name="taxRate"
              value="#{@taxPolicy.currentRate}"/>
</bean>
~~~

Ở đây, @taxPolicy tham chiếu bean có tên taxPolicy. Expression đọc property currentRate trên bean đó và gán kết quả cho taxRate.

Nếu chỉ cần inject trực tiếp một bean vào property có kiểu tương thích, thuộc tính ref thường đơn giản và rõ ràng hơn:

~~~xml
<property name="taxPolicy" ref="taxPolicy"/>
~~~

Dùng SpEL khi cần lấy một giá trị, gọi một phép tính hoặc kết hợp bean với dữ liệu khác. Dùng ref khi mục đích chỉ là inject bean trực tiếp.

## 3. Dùng expression trong constructor argument

SpEL cũng có thể cung cấp giá trị cho constructor argument:

~~~xml
<bean id="retryPolicy" class="com.example.RetryPolicy">
    <constructor-arg value="#{3 * 2}"/>
    <constructor-arg value="#{T(java.time.Duration).ofSeconds(30)}"/>
</bean>
~~~

Ví dụ này truyền kết quả phép tính 6 và một Duration 30 giây vào constructor tương ứng.

Có thể tham chiếu bean trong constructor argument:

~~~xml
<bean id="reportService" class="com.example.ReportService">
    <constructor-arg value="#{@reportSettings.outputDirectory}"/>
</bean>
~~~

Spring đánh giá giá trị expression trong quá trình giải quyết bean definition rồi sử dụng kết quả làm đối số. Kiểu đích của constructor parameter và conversion service ảnh hưởng tới việc chuyển kết quả sang kiểu cần thiết.

Nếu có nhiều constructor overload, hãy đảm bảo số lượng và kiểu argument đủ rõ để Spring chọn đúng constructor. Với cấu hình phức tạp, có thể dùng constructor-arg index hoặc type để làm rõ mapping, và kiểm thử việc khởi tạo context.

## 4. Tham chiếu bean bằng @beanName

Trong SpEL, ký hiệu **@** dùng để tham chiếu bean theo tên:

~~~text
@taxPolicy
@systemClock
@featureSettings.enabled
~~~

Ví dụ:

~~~xml
<bean id="invoiceSettings" class="com.example.InvoiceSettings">
    <property name="taxPolicy" value="#{@taxPolicy}"/>
    <property name="taxRate" value="#{@taxPolicy.currentRate}"/>
</bean>
~~~

Expression đầu tiên trả về bean taxPolicy. Expression thứ hai đọc currentRate từ bean đó.

Bean reference trong expression cần bean expression context có BeanResolver phù hợp. Trong ApplicationContext của Spring, việc đánh giá bean definition được tích hợp với bean factory để phân giải các bean reference.

Cần phân biệt:

- ref="taxPolicy" là cơ chế XML dependency reference trực tiếp.
- value="#{@taxPolicy}" là SpEL expression trả về bean taxPolicy.
- value="#{@taxPolicy.currentRate}" là SpEL expression truy cập property của bean.

Không dùng bean reference qua SpEL chỉ để thay thế một ref đơn giản. Expression có ích khi cần kết hợp bean với phép tính hoặc lấy một phần giá trị của bean.

## 5. Dùng static type reference trong XML

SpEL cho phép dùng **T(...)** để tham chiếu class Java, từ đó truy cập static field, enum constant hoặc static method.

~~~xml
<bean id="mathSettings" class="com.example.MathSettings">
    <property name="pi" value="#{T(java.lang.Math).PI}"/>
    <property name="maxInteger" value="#{T(java.lang.Integer).MAX_VALUE}"/>
</bean>
~~~

Có thể dùng enum constant:

~~~xml
<bean id="jobSettings" class="com.example.JobSettings">
    <property name="roundingMode"
              value="#{T(java.math.RoundingMode).HALF_UP}"/>
</bean>
~~~

Hoặc gọi static method:

~~~xml
<property name="defaultDate"
          value="#{T(java.time.LocalDate).of(2026, 11, 12)}"/>
~~~

Với class ngoài java.lang, nên dùng tên đầy đủ package để tránh phụ thuộc import prefix của TypeLocator. Type reference chỉ giải quyết class; class phải có trên runtime classpath và context phải hỗ trợ type resolution.

## 6. Expression trong collection và map

SpEL có thể được dùng trong các giá trị con của collection trong XML bean definition.

Ví dụ list:

~~~xml
<bean id="notificationSettings"
      class="com.example.NotificationSettings">
    <property name="channels">
        <list>
            <value>EMAIL</value>
            <value>SMS</value>
            <value>#{@featureSettings.defaultChannel}</value>
        </list>
    </property>
</bean>
~~~

Ví dụ map:

~~~xml
<bean id="thresholdSettings"
      class="com.example.ThresholdSettings">
    <property name="thresholds">
        <map>
            <entry key="standard" value="#{100 * 2}"/>
            <entry key="premium"
                   value="#{@pricingPolicy.premiumThreshold}"/>
        </map>
    </property>
</bean>
~~~

Expression có thể cung cấp key hoặc value nếu kiểu đích và cấu trúc XML cho phép:

~~~xml
<entry key="#{@regionSettings.code}"
       value="#{@regionSettings.displayName}"/>
~~~

Khi dùng collection, cần xác định kiểu phần tử và kiểu key/value mong muốn. Spring có thể thực hiện conversion cho phần tử khi cần, nhưng dữ liệu không hợp lệ hoặc converter thiếu vẫn có thể làm quá trình tạo bean thất bại.

Với collection lồng nhau, expression được đánh giá tại từng vị trí có giá trị được Spring giải quyết. Nếu cấu hình trở nên dài hoặc có nhiều phép tính, hãy cân nhắc tạo một bean cấu hình Java có tên thuộc tính rõ ràng.

## 7. Phân biệt SpEL #{...} với property placeholder

Spring XML thường có hai cơ chế dễ bị nhầm:

| Cú pháp | Mục đích | Ví dụ |
|---|---|---|
| PLACEHOLDER | Lấy giá trị từ property source hoặc placeholder configurer | service.timeout |
| SPEL | Đánh giá một SpEL expression | 30 * 2 |

Property placeholder thường lấy giá trị cấu hình từ file properties, environment hoặc nguồn cấu hình đã đăng ký. SpEL thực hiện phép tính, truy cập object, gọi method hoặc kết hợp dữ liệu trong expression.

Ví dụ dùng placeholder:

~~~xml
<property name="timeout" value="${service.timeout}"/>
~~~

Ví dụ dùng SpEL:

~~~xml
<property name="timeout" value="#{30 * 2}"/>
~~~

Nếu ứng dụng đã cấu hình placeholder resolution, có thể dùng giá trị cấu hình làm đầu vào cho expression:

~~~xml
<property name="timeout"
          value="#{${service.timeout:30} * 2}"/>
~~~

Ở ví dụ này, placeholder cung cấp giá trị cấu hình hoặc default 30; sau đó SpEL nhân giá trị đã được thay thế với 2. Việc kết hợp cần được kiểm thử với đúng PropertySourcesPlaceholderConfigurer hoặc cơ chế placeholder của ứng dụng.

Không thay placeholder bằng SpEL một cách máy móc. Nếu chỉ cần đọc một property cấu hình, placeholder thường phù hợp hơn. Dùng SpEL khi cần biểu thức hoặc truy cập đối tượng.

## 8. Escape ký tự đặc biệt trong XML

Một SpEL expression nằm bên trong XML vẫn phải tuân thủ cú pháp XML. XML parser xử lý ký tự trước khi Spring đánh giá expression.

Một số ký tự cần chú ý:

| Ký tự cần có trong expression | Viết trong XML |
|---|---|
| < | &lt; |
| & | &amp; |
| > | Có thể viết &gt; để rõ ràng |
| " trong thuộc tính dùng dấu nháy kép | &quot; |
| ' trong thuộc tính dùng dấu nháy đơn | &apos; |

Ví dụ so sánh nhỏ hơn trong thuộc tính value:

~~~xml
<property name="eligible"
          value="#{#root.score &lt; 80}"/>
~~~

Sau khi XML parser giải mã entity, SpEL nhận biểu thức có toán tử nhỏ hơn.

Ví dụ dùng AND:

~~~xml
<property name="eligible"
          value="#{#root.active and #root.score &gt;= 80}"/>
~~~

Dùng từ khóa and giúp tránh phải viết toán tử ampersand kép trong XML. Nếu cần dùng &&, phải viết thành &amp;&amp; trong tài liệu XML để XML parser tạo lại && trước khi SpEL xử lý.

Với string literal bên trong thuộc tính XML dùng dấu nháy kép, hãy dùng dấu nháy đơn của SpEL:

~~~xml
<property name="label" value="#{'Ready'}"/>
~~~

Nếu giá trị literal cần chứa dấu nháy kép, có thể dùng entity XML phù hợp hoặc chuyển sang phần tử XML có nội dung text. Luôn phân biệt lớp escape của XML với cú pháp string literal của SpEL.

## 9. XML element content và CDATA

Expression có thể nằm trong thuộc tính XML hoặc trong nội dung text của phần tử, tùy cấu trúc bean definition. XML vẫn áp dụng quy tắc escape tương ứng.

Ví dụ một giá trị trong element:

~~~xml
<property name="description">
    <value>#{'A &amp; B'}</value>
</property>
~~~

XML parser chuyển &amp; thành ký tự ampersand trước khi Spring xử lý giá trị.

CDATA có thể giữ một số ký tự XML như văn bản mà không cần viết entity, nhưng không nên giả định CDATA thay đổi cú pháp SpEL hoặc tắt việc đánh giá expression. Spring vẫn nhận giá trị chuỗi sau khi XML parser xử lý tài liệu và có thể đánh giá expression delimiter trong chuỗi đó.

Với XML có nhiều ký tự đặc biệt, chọn cách biểu diễn dễ đọc và kiểm thử được. Tránh trộn nhiều lớp escape mà không xác nhận chuỗi thực tế Spring nhận được.

## 10. Khi nào expression được đánh giá?

SpEL trong bean definition được đánh giá khi Spring giải quyết các giá trị của bean definition trong quá trình tạo bean. Vì vậy, expression không nhất thiết được đánh giá mỗi lần ứng dụng gọi một method trên bean.

Với singleton bean, giá trị expression thường được giải quyết khi bean được tạo và giữ trong instance singleton. Với prototype bean, quá trình tạo bean lặp lại có thể khiến giá trị expression được đánh giá lại trong mỗi lần tạo instance.

Ví dụ, nếu property singleton được cấu hình bằng:

~~~xml
<property name="startupTime"
          value="#{T(java.time.Instant).now()}"/>
~~~

giá trị được gán khi bean được tạo. Nó không tự cập nhật ở mỗi lần đọc property.

Nếu expression tham chiếu một bean khác hoặc một object mutable, bean được tham chiếu có thể thay đổi state sau đó; nhưng giá trị scalar đã tính và gán vào property không tự động tính lại chỉ vì nguồn thay đổi.

Nếu cần tính giá trị động mỗi lần sử dụng, hãy gọi một method của bean trong Java thay vì dựa vào một expression được giải quyết lúc khởi tạo bean.

## 11. Cấu hình bean expression resolver

ApplicationContext của Spring thường cấu hình sẵn bean expression resolver cho bean definition values. Khi dùng một BeanFactory được tạo thủ công hoặc cấu hình đặc biệt, cần bảo đảm bean expression resolver được đăng ký nếu muốn đánh giá #{...}.

Bean expression resolver cung cấp ngữ cảnh đánh giá cho biểu thức trong bean definition, bao gồm khả năng truy cập bean factory và các biến môi trường mà integration cung cấp.

Nếu expression trong XML không được đánh giá mà được gán nguyên chuỗi #{...} vào property, hãy kiểm tra:

- Ứng dụng có dùng ApplicationContext phù hợp không.
- BeanExpressionResolver có được cấu hình không.
- Giá trị có thực sự đi qua cơ chế resolve bean definition string không.
- XML có được nạp bằng Spring container hay chỉ được đọc như tài liệu XML thông thường.
- Có cấu hình tùy chỉnh thay thế resolver mặc định hay không.

Không tự tạo một EvaluationContext rời rạc rồi kỳ vọng XML bean definition tự dùng context đó. Expression resolver của bean factory là thành phần xử lý expression trong quá trình tạo bean.

## 12. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Giá trị #{...} được giữ nguyên như text | Bean expression resolver không được áp dụng | Kiểm tra ApplicationContext và resolver |
| XML không parse được | Ký tự <, & hoặc dấu nháy không được escape | Sửa XML entity hoặc cấu trúc thuộc tính |
| Expression parse thất bại | Cú pháp SpEL sai hoặc delimiter không cân bằng | Kiểm tra phần bên trong #{...} |
| Không tìm thấy bean | Bean name sai hoặc bean chưa được đăng ký | Kiểm tra bean definition và tên tham chiếu @beanName |
| Không tìm thấy class | Sai fully qualified name hoặc thiếu dependency | Kiểm tra runtime classpath và TypeLocator |
| Constructor/property không nhận kiểu kết quả | Conversion không phù hợp | Kiểm tra target type và ConversionService |
| Placeholder không được thay thế | Placeholder configurer hoặc property source chưa được cấu hình | Kiểm tra placeholder resolution riêng với SpEL |
| Biểu thức trả giá trị cũ | Giá trị được tính khi bean được tạo, không phải mỗi lần đọc | Xác định scope và thời điểm tạo bean |
| Bean khởi tạo thất bại | Expression ném lỗi khi resolve property/constructor value | Đọc cause chain và kiểm tra expression cùng dữ liệu |

Khi chẩn đoán, tách lỗi theo lớp:

1. XML parsing.
2. Property placeholder resolution.
3. SpEL parsing.
4. Bean/type resolution.
5. Evaluation và conversion.
6. Bean instantiation hoặc property assignment.

Cách tách này giúp xác định lỗi thuộc XML, cấu hình Spring hay expression thay vì thay đổi nhiều phần cùng lúc.

## 13. Kiểm thử SpEL trong XML bean definition

Nên kiểm thử bằng cách nạp chính XML configuration trong một ApplicationContext test. Điều này xác nhận cả XML parsing, placeholder processing, SpEL evaluation và bean creation.

Ví dụ:

~~~java
@Test
void evaluatesSpelInXmlBeanDefinition() {
    try (ClassPathXmlApplicationContext context =
            new ClassPathXmlApplicationContext(
                "spel-beans.xml")) {

        PricingSettings settings =
            context.getBean("pricingSettings", PricingSettings.class);

        assertEquals(
            BigDecimal.valueOf(500),
            settings.getMaximumPrice()
        );
    }
}
~~~

Ngoài kiểm thử bean được tạo thành công, nên kiểm tra:

- Property value từ một expression đơn giản.
- Constructor argument được tính bằng expression.
- Bean reference và property access qua @beanName.
- Static field, enum constant và static method.
- Collection entry có expression.
- XML entity cho <, & và dấu nháy.
- Placeholder riêng và placeholder kết hợp với SpEL.
- Lỗi khi bean hoặc class không tồn tại.
- Lỗi conversion khi kiểu kết quả không phù hợp.
- Thời điểm expression được đánh giá với singleton và prototype nếu điều đó ảnh hưởng nghiệp vụ.

Nếu dùng XML namespace hoặc placeholder configurer, test cần nạp đúng cấu hình namespace và property source như production. Chỉ parse expression bằng SpelExpressionParser không đủ để xác nhận toàn bộ đường đi của XML bean definition.

## 14. Thực hành tốt

- Dùng #{...} khi cần SpEL trong giá trị bean definition.
- Dùng ref cho dependency injection trực tiếp; dùng @beanName khi expression cần tham chiếu bean như một phần của phép tính.
- Dùng placeholder cho property cấu hình và #{...} cho SpEL.
- Dùng fully qualified class name trong type reference khi cần rõ ràng.
- Giữ expression ngắn, dễ đọc và không chứa logic nghiệp vụ nhiều bước.
- Escape ký tự XML trước khi Spring nhận được expression.
- Dùng and/or khi muốn tránh ampersand kép trong XML.
- Không giả định expression được tính lại mỗi lần đọc property.
- Kiểm tra scope và thời điểm tạo bean khi expression phụ thuộc dữ liệu thay đổi.
- Dùng ApplicationContext test để xác nhận XML, placeholder, SpEL và bean creation cùng hoạt động.
- Không đưa expression không đáng tin cậy vào bean definition có quyền truy cập rộng.
- Chuyển logic động hoặc phức tạp sang Java service/method có thể kiểm thử.

## 15. Checklist review

Trước khi đưa SpEL vào XML bean definition, hãy kiểm tra:

- [ ] Expression dùng đúng delimiter #{...}.
- [ ] XML được parse hợp lệ trước khi Spring xử lý.
- [ ] Ký tự <, & và dấu nháy được escape đúng lớp.
- [ ] Property value và constructor argument có kiểu kết quả phù hợp.
- [ ] Bean reference dùng đúng tên và bean đã được đăng ký.
- [ ] Type reference dùng đúng class có trên runtime classpath.
- [ ] Collection key/value có kiểu và conversion mong muốn.
- [ ] Placeholder được phân biệt với SpEL.
- [ ] Placeholder configurer và property source được cấu hình nếu cần.
- [ ] Bean expression resolver được áp dụng.
- [ ] Thời điểm expression được đánh giá phù hợp với scope của bean.
- [ ] Có integration test nạp XML bằng ApplicationContext.

## Kết luận

SpEL trong XML bean definition dùng delimiter **#{...}** để đánh giá expression và đưa kết quả vào property, constructor argument hoặc collection value khi Spring tạo bean. Expression có thể đọc system properties, gọi static member và tham chiếu bean qua @beanName. Hãy phân biệt SpEL với property placeholder, escape ký tự theo quy tắc XML, và nhớ rằng giá trị thường được tính trong quá trình tạo bean chứ không tự động cập nhật mỗi lần đọc. Kiểm thử bằng cách nạp XML trong ApplicationContext để xác nhận toàn bộ quá trình parsing, resolution, conversion và bean creation.