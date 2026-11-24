# Registering ControllerAdvice, Converters, and Validators

**Context:** Spring Framework Testing → MockMvc Setup.

When testing Spring MVC with MockMvc, a request passes through multiple components before a controller returns a response. Spring must locate a matching handler, convert input data, invoke the controller, handle errors, and convert the result into an HTTP response. Therefore, a test that only instantiates a controller may miss important application behaviors.

Three groups of components often need explicit registration when setting up MockMvc:

- **ControllerAdvice:** handles exceptions and cross-cutting concerns shared across multiple controllers.
- **Converter and HttpMessageConverter:** convert request values into Java types or convert Java objects into response content.
- **Validator:** validates input data against Bean Validation rules or business rules.

How you register them depends on whether the test uses **standaloneSetup** or **webAppContextSetup**. Choosing the right approach ensures the test accurately reflects the scope it aims to verify.

## 1. Which Components Does MockMvc Need?

MockMvc simulates Spring MVC request processing in a test environment. It invokes DispatcherServlet and the configured MVC components, then lets you assert status codes, headers, body, and other processing results without opening a real HTTP port.

A request can flow through the following general path:

~~~text
MockMvc request
      |
      v
DispatcherServlet
      |
      v
HandlerMapping finds Controller method
      |
      v
HandlerAdapter prepares arguments
      |
      +--> HttpMessageConverter reads request body
      |
      +--> ConversionService converts path/query/form value
      |
      +--> Validator checks data marked for validation
      |
      v
Controller method
      |
      +--> Exception? ----> ControllerAdvice / HandlerExceptionResolver
      |
      v
HttpMessageConverter writes response body
      |
      v
MockMvc ResultActions and assertions
~~~

This is a general flow. Specific steps depend on parameter types, annotations on handler methods, and MVC configuration.

If a component is omitted from the MockMvc configuration, the test may fail to exhibit real application behavior. For example, a controller may run normally, yet a business error is not mapped to HTTP 404 because the advice was not registered; or a query parameter status=paid cannot be converted to an enum because a custom converter was not added.

## 2. Two Ways to Set Up MockMvc and Their Impact on Registration

Spring Test provides two commonly used setup approaches.

| Setup Approach | How MVC Infrastructure Is Created | When It Fits |
|---|---|---|
| standaloneSetup(...) | Creates minimal MVC configuration for specified controllers | Tests focused on one or a few controllers, explicitly declaring MVC dependencies |
| webAppContextSetup(context) | Uses a configured WebApplicationContext | Integration tests of controllers with the application's actual MVC configuration |

### 2.1. standaloneSetup

Example:

~~~java
MockMvc mockMvc = MockMvcBuilders
        .standaloneSetup(new OrderController())
        .build();
~~~

This approach does not start the entire application context. MockMvc builds the infrastructure needed for the passed-in controllers. This is a fast choice for controller tests, but custom application components must be supplied explicitly when the test depends on them.

Key configuration methods include:

- setControllerAdvice(...)
- setMessageConverters(...)
- setConversionService(...)
- setValidator(...)
- setCustomArgumentResolvers(...)
- setHandlerExceptionResolvers(...)

You do not need to register all of them in every test. Register only the components that the test's requests require.

### 2.2. webAppContextSetup

Example:

~~~java
MockMvc mockMvc = MockMvcBuilders
        .webAppContextSetup(webApplicationContext)
        .build();
~~~

This approach uses beans and MVC infrastructure from WebApplicationContext. If ControllerAdvice, WebMvcConfigurer, converters, and validators are properly configured in the context, MockMvc can use them just like the configured MVC application.

A plain Spring Framework test can load a web context using:

~~~java
@ExtendWith(SpringExtension.class)
@WebAppConfiguration
@ContextConfiguration(classes = MvcTestConfig.class)
class OrderControllerWebMvcTest {

    @Autowired
    WebApplicationContext webApplicationContext;

    MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        mockMvc = MockMvcBuilders
                .webAppContextSetup(webApplicationContext)
                .build();
    }
}
~~~

**@WebAppConfiguration** instructs Spring Test to create a WebApplicationContext. **@ContextConfiguration** specifies the configuration used to create the context; that configuration must register the controllers and MVC components under test.

If the goal is to verify component registration within the application configuration, webAppContextSetup is usually a better fit because it exercises the same MVC configuration the application uses. If the goal is to test controller behavior in isolation with a small setup, standaloneSetup keeps the test more focused.

## 3. Registering ControllerAdvice

### 3.1. What Problem Does ControllerAdvice Solve?

**@ControllerAdvice** defines shared concerns across multiple controllers. Common capabilities include:

- Handling exceptions with @ExceptionHandler.
- Registering @InitBinder methods to customize data binding.
- Providing shared model data with @ModelAttribute.

**@RestControllerAdvice** combines @ControllerAdvice and @ResponseBody, making it suitable when handlers return data in the response body, such as JSON.

Example of an advice that maps a missing-order error to HTTP 404:

~~~java
@RestControllerAdvice
class ApiExceptionHandler {

    @ExceptionHandler(OrderNotFoundException.class)
    ResponseEntity<ApiError> handleOrderNotFound(
            OrderNotFoundException exception) {

        return ResponseEntity
                .status(HttpStatus.NOT_FOUND)
                .body(new ApiError(
                        "ORDER_NOT_FOUND",
                        exception.getMessage()
                ));
    }
}

record ApiError(String code, String message) {}
~~~

When the controller throws OrderNotFoundException, Spring finds the matching exception handler and builds the response. Tests should send requests through MockMvc to verify the entire exception-mapping process, rather than calling handleOrderNotFound directly.

### 3.2. Registering Advice with standaloneSetup

With standaloneSetup, pass the advice to the builder:

~~~java
MockMvc mockMvc = MockMvcBuilders
        .standaloneSetup(new OrderController())
        .setControllerAdvice(new ApiExceptionHandler())
        .build();
~~~

Multiple advice instances can be passed:

~~~java
MockMvc mockMvc = MockMvcBuilders
        .standaloneSetup(new OrderController())
        .setControllerAdvice(
                new ApiExceptionHandler(),
                new ValidationExceptionHandler()
        )
        .build();
~~~

Each passed object must be an instance carrying the appropriate annotations and handler methods. Because standalone setup does not component-scan the application, merely annotating a class with @ControllerAdvice does not mean its instance is automatically discovered in a standalone setup.

If a controller depends on services, pass mock or fake dependencies into the constructor/controller according to how the project is structured. You do not need to spin up an application context just to register an advice for a controller test.

### 3.3. Registering Advice with webAppContextSetup

In a setup using WebApplicationContext, the advice must be a bean managed by the context. It can be declared explicitly as a bean:

~~~java
@Configuration
@EnableWebMvc
class MvcTestConfig {

    @Bean
    OrderController orderController() {
        return new OrderController();
    }

    @Bean
    ApiExceptionHandler apiExceptionHandler() {
        return new ApiExceptionHandler();
    }
}
~~~

Or via component scanning on the packages containing controllers and advice:

~~~java
@Configuration
@EnableWebMvc
@ComponentScan(basePackageClasses = {
        OrderController.class,
        ApiExceptionHandler.class
})
class MvcTestConfig {
}
~~~

Once the context initializes, create MockMvc:

~~~java
mockMvc = MockMvcBuilders
        .webAppContextSetup(webApplicationContext)
        .build();
~~~

There is no need to additionally call setControllerAdvice if the advice is already registered properly in the context. Passing a different advice instance again may mean the test is testing a configuration different from the actual bean configuration.

### 3.4. Choosing the Scope of ControllerAdvice

By default, @ControllerAdvice can apply to many controllers across the application. Its scope can be narrowed using attributes:

- basePackages or basePackageClasses: apply by package.
- assignableTypes: apply to controllers of the specified types.
- annotations: apply to controllers carrying the specified annotations.

Example:

~~~java
@RestControllerAdvice(basePackageClasses = PublicApiMarker.class)
class PublicApiExceptionHandler {
    // Exception handlers apply only to the corresponding controller group.
}
~~~

When multiple advice beans exist, ordering can be controlled with @Order or Ordered. Controller-level @ExceptionHandler methods are considered before global advice. Within an advice, a direct exception match generally takes precedence over a cause-based match. Because ordering across multiple advice beans affects which handler is chosen, tests should explicitly assert the response when multiple handlers could match.

Avoid creating multiple advice classes with overlapping scopes that handle the same exception type without clear ordering rules.

### 3.5. Testing the Result of ControllerAdvice

Example:

~~~java
@Test
void mapsOrderNotFoundToNotFoundResponse() throws Exception {
    mockMvc.perform(get("/orders/404"))
            .andExpect(status().isNotFound())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.code").value("ORDER_NOT_FOUND"));
}
~~~

This test verifies three things:

1. The request reaches the controller and produces the expected exception.
2. The advice handles that exception and returns HTTP 404.
3. The response body is serialized as JSON with the expected error code.

If a test only calls controller.findOrder(404) and asserts that the exception is thrown, it has not tested ControllerAdvice or HTTP response generation.

## 4. Distinguishing Converter and HttpMessageConverter

In Spring MVC, the word "converter" often refers to two different groups. You must distinguish them when registering and writing tests.

| Component | Job | Example |
|---|---|---|
| HttpMessageConverter<T> | Reads or writes the entire HTTP message body | JSON to DTO, DTO to JSON |
| Converter<S, T> | Converts a single value from a source type to a target type | String paid to enum OrderStatus |
| Formatter<T> | Converts values by format, often with locale support | Date string to LocalDate |

HttpMessageConverter works with bodies and media types such as application/json. Converter and Formatter usually participate in binding values from path variables, query parameters, or form fields.

Registering a Converter<String, OrderStatus> does not replace the Jackson message converter. Conversely, configuring Jackson does not automatically register rules for converting query parameters into enums in an application-specific format.

## 5. Registering HttpMessageConverter

### 5.1. Role of HttpMessageConverter

Spring MVC uses HttpMessageConverter to:

- Read a request body into a Java object for @RequestBody.
- Write a Java object into a response body for @ResponseBody or @RestController.
- Select reading/writing strategies based on media type, such as JSON or XML.

With Jackson on the classpath, MappingJackson2HttpMessageConverter typically handles JSON. Applications may need custom converters for specialized formats or data types.

Example endpoint accepting JSON:

~~~java
@PostMapping("/orders")
ResponseEntity<OrderResponse> create(
        @RequestBody CreateOrderRequest request) {
    // Process the request and return OrderResponse.
}
~~~

If a JSON converter is not registered or does not support the request's media type, Spring may return 415 Unsupported Media Type or a body-reading error depending on the situation.

### 5.2. Registering in standaloneSetup

Use setMessageConverters(...):

~~~java
MappingJackson2HttpMessageConverter jsonConverter =
        new MappingJackson2HttpMessageConverter();

MockMvc mockMvc = MockMvcBuilders
        .standaloneSetup(new OrderController())
        .setMessageConverters(jsonConverter)
        .build();
~~~

Note: when calling setMessageConverters, the provided list of converters becomes the converter list used by the standalone builder. If the application also needs converters for String, byte array, XML, or other body types, the test must provide the needed converters. Do not assume MVC's default converters are still appended automatically.

If you need Jackson configured like the real application, pass the configured ObjectMapper:

~~~java
ObjectMapper objectMapper = new ObjectMapper();
// Register modules and serialization configuration required by the application.

MappingJackson2HttpMessageConverter jsonConverter =
        new MappingJackson2HttpMessageConverter(objectMapper);
~~~

For Java Time, the appropriate Jackson module must be on the classpath and registered according to the project's configuration. In integration tests using webAppContextSetup, the converter created by the MVC configuration is used instead of having to rebuild it separately in each test.

### 5.3. Registering in WebMvcConfigurer

In Spring MVC configuration, there are two common extension points:

- configureMessageConverters(...): configures the converter list; when you add converters to this list, you take responsibility for the list used.
- extendMessageConverters(...): modifies or adds converters after the default list has been built.

If you only want to add a custom converter while keeping the default converters, extendMessageConverters is usually suitable:

~~~java
@Configuration
@EnableWebMvc
class MvcConfig implements WebMvcConfigurer {

    @Override
    public void extendMessageConverters(
            List<HttpMessageConverter<?>> converters) {

        converters.add(0, new CustomReportMessageConverter());
    }
}
~~~

Position in the list can affect which converter is chosen when multiple converters support the media type and data type. Place a specialized converter before a general converter when that is the intentional requirement. Do not add duplicate converters or alter the order without understanding the impact.

### 5.4. Testing Request and Response Bodies

Example testing an endpoint that accepts JSON:

~~~java
@Test
void readsJsonRequestAndWritesJsonResponse() throws Exception {
    mockMvc.perform(post("/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .accept(MediaType.APPLICATION_JSON)
                    .content("""
                            {
                              "customerName": "An"
                            }
                            """))
            .andExpect(status().isCreated())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.customerName").value("An"));
}
~~~

contentType describes the format of the outgoing body; accept describes the response format the client expects. jsonPath verifies the JSON structure written out.

To test that the converter is actually used, send the body via MockMvcRequestBuilders and let Spring read the body. Calling ObjectMapper.readValue manually in the test does not verify MVC's HttpMessageConverter registration.

## 6. Registering Converter and Formatter for Data Binding

### 6.1. Converter for Single-Value Conversion

Suppose an API receives query parameter status=paid, while the Java enum uses PAID:

~~~java
enum OrderStatus {
    NEW,
    PAID,
    CANCELLED
}
~~~

Create the converter:

~~~java
final class StringToOrderStatusConverter
        implements Converter<String, OrderStatus> {

    @Override
    public OrderStatus convert(String source) {
        return OrderStatus.valueOf(
                source.trim().toUpperCase(Locale.ROOT)
        );
    }
}
~~~

This converter normalizes the input string and converts it into an enum. Locale.ROOT ensures uppercasing does not depend on the default locale of the machine running the test.

If the string does not match an enum value, valueOf throws IllegalArgumentException; Spring binding can translate that into a type mismatch error. If the API requires a friendly message or custom error code, appropriate exception handling can be added.

### 6.2. Registering Converter in standaloneSetup

The standalone builder accepts a FormattingConversionService:

~~~java
DefaultFormattingConversionService conversionService =
        new DefaultFormattingConversionService();

conversionService.addConverter(new StringToOrderStatusConverter());

MockMvc mockMvc = MockMvcBuilders
        .standaloneSetup(new OrderController())
        .setConversionService(conversionService)
        .build();
~~~

DefaultFormattingConversionService provides common formatting conversions and lets you add custom converters. When passing a custom conversion service, the test must ensure it includes all formatters and converters required by the handler.

### 6.3. Registering Converter in WebMvcConfigurer

With an MVC context, register via addFormatters:

~~~java
@Configuration
@EnableWebMvc
class MvcConfig implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(new StringToOrderStatusConverter());
    }
}
~~~

Spring MVC uses the conversion service to convert bound values such as:

- @PathVariable
- @RequestParam
- @ModelAttribute
- Fields of form objects

Example controller:

~~~java
@GetMapping("/orders")
Map<String, String> findByStatus(
        @RequestParam OrderStatus status) {

    return Map.of("status", status.name());
}
~~~

Test:

~~~java
@Test
void convertsLowercaseQueryParameterToEnum() throws Exception {
    mockMvc.perform(get("/orders").param("status", "paid"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("PAID"));
}
~~~

If the converter is not registered, the string paid may fail to convert into the enum and the request fails before the controller method is invoked. Testing through MockMvc verifies the parameter binding step as well.

### 6.4. When Should You Use Formatter?

Formatter<T> fits when converting a data type that has display/input formatting rules and may depend on locale. For example, formatting a date entered from a form.

~~~java
final class LocalDateFormatter implements Formatter<LocalDate> {

    private final DateTimeFormatter formatter =
            DateTimeFormatter.ofPattern("dd/MM/yyyy");

    @Override
    public LocalDate parse(String text, Locale locale) {
        return LocalDate.parse(text, formatter);
    }

    @Override
    public String print(LocalDate object, Locale locale) {
        return formatter.format(object);
    }
}
~~~

Register with:

~~~java
@Override
public void addFormatters(FormatterRegistry registry) {
    registry.addFormatter(new LocalDateFormatter());
}
~~~

In a real application, if formatting depends on locale, the formatter should use the passed-in locale instead of hardcoding a single pattern. The example above illustrates the registration point and can be extended to match the application's input rules.

## 7. Registering Validator

### 7.1. What Is the Role of Validator?

A Validator checks whether bound or deserialized data satisfies rules. Spring supports:

- Spring's org.springframework.validation.Validator.
- Jakarta Bean Validation via annotations such as @NotBlank, @Size, @Email, @Min.
- Validation groups and custom rules.

With Spring Framework 6 and Spring Boot 3, Bean Validation uses the jakarta.validation.* package. The project needs a Jakarta Bean Validation implementation, typically Hibernate Validator, on the classpath. Having annotations without a matching provider is not enough to execute validation.

Example request DTO:

~~~java
public record CreateOrderRequest(
        @NotBlank
        @Size(max = 100)
        String customerName
) {}
~~~

Controller requiring validation:

~~~java
@PostMapping("/orders")
ResponseEntity<Map<String, String>> create(
        @Valid @RequestBody CreateOrderRequest request) {

    return ResponseEntity
            .status(HttpStatus.CREATED)
            .body(Map.of("customerName", request.customerName()));
}
~~~

@Valid asks Spring to run validation on the object created from the request body. If errors occur, Spring MVC raises MethodArgumentNotValidException before invoking the controller method body.

### 7.2. Registering Validator in standaloneSetup

You can use LocalValidatorFactoryBean as the validator:

~~~java
LocalValidatorFactoryBean validator =
        new LocalValidatorFactoryBean();

validator.afterPropertiesSet();

MockMvc mockMvc = MockMvcBuilders
        .standaloneSetup(new OrderController())
        .setValidator(validator)
        .build();
~~~

LocalValidatorFactoryBean bridges Jakarta Bean Validation with Spring's org.springframework.validation.Validator interface. In a standalone example, the bean must be initialized before being passed to the builder.

If the project uses a custom validator implementing Spring Validator, that instance can be passed directly. The validator must support the object type the controller needs to validate.

### 7.3. Registering Validator in WebMvcConfigurer

In MVC configuration, override getValidator():

~~~java
@Configuration
@EnableWebMvc
class MvcConfig implements WebMvcConfigurer {

    @Bean
    LocalValidatorFactoryBean mvcValidator() {
        return new LocalValidatorFactoryBean();
    }

    @Override
    public Validator getValidator() {
        return mvcValidator();
    }
}
~~~

The MVC infrastructure uses this validator for data binding and validation. In real configurations, ensure the bean is created and managed by the Spring context. If no custom validator is needed, Spring MVC can configure a default validator when a Bean Validation provider is present.

Another approach is registering validators per binder via @InitBinder. This is useful when rules apply only to a specific group of controllers or a specific form type.

### 7.4. Using @InitBinder to Add Validators

Example:

~~~java
@ControllerAdvice
class OrderBindingAdvice {

    @InitBinder
    void configureOrderBinder(WebDataBinder binder) {
        binder.addValidators(new OrderBusinessValidator());
    }
}
~~~

addValidators appends a validator to the existing binder. If you use setValidator, the binder's primary validator may be replaced; choose the right method for your intent and check whether default Bean Validation needs to be retained.

@InitBinder can also register property editors or binding settings. When placed inside @ControllerAdvice, the binder method can apply to multiple controllers within the advice's scope.

### 7.5. Distinguishing Validation Errors from Binding Errors

These two error groups are related but not identical:

- **Validation error:** the data has been converted into an object, but violates rules such as an empty name or exceeding a length limit.
- **Binding/conversion error:** Spring cannot convert the input value to the target type, for example status=unknown cannot be converted into OrderStatus.

For @Valid @RequestBody, Bean Validation failures are typically represented by MethodArgumentNotValidException. For request parameters or model attributes, conversion errors may be represented as MethodArgumentTypeMismatchException, BindException, or the corresponding binding error.

Spring Framework 6.1 also includes method validation for constraints placed directly on handler method parameters or return values; errors may be represented by HandlerMethodValidationException. When building a unified API error response, handle the exact exception types the application actually throws.

### 7.6. Testing Validation

Example invalid request:

~~~java
@Test
void rejectsBlankCustomerName() throws Exception {
    mockMvc.perform(post("/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {
                              "customerName": " "
                            }
                            """))
            .andExpect(status().isBadRequest());
}
~~~

To test an error response standardized by advice, a handler can be added:

~~~java
@ExceptionHandler(MethodArgumentNotValidException.class)
ResponseEntity<ApiError> handleValidation(
        MethodArgumentNotValidException exception) {

    String detail = exception.getBindingResult()
            .getFieldErrors()
            .stream()
            .map(error -> error.getField() + ": "
                    + error.getDefaultMessage())
            .findFirst()
            .orElse("Invalid request");

    return ResponseEntity
            .badRequest()
            .body(new ApiError("VALIDATION_FAILED", detail));
}
~~~

Then test the response:

~~~java
@Test
void returnsStandardErrorWhenRequestValidationFails()
        throws Exception {

    mockMvc.perform(post("/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {
                              "customerName": ""
                            }
                            """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                    .value("VALIDATION_FAILED"))
            .andExpect(jsonPath("$.message")
                    .value(org.hamcrest.Matchers.containsString(
                            "customerName")));
}
~~~

This test verifies all three components working together: Jackson reads the JSON, Validator checks the DTO, and ControllerAdvice maps the error into a response conforming to the API contract.

## 8. Example Combining All Three Components in Standalone MockMvc

This section combines the ideas above into a focused test setup for OrderController.

Suppose the controller has the following behaviors:

- GET /orders?status=paid: accepts an enum via query parameter.
- GET /orders/404: throws OrderNotFoundException.
- POST /orders: accepts JSON and requires customerName not to be blank.

### 8.1. Controller and Data Types

~~~java
enum OrderStatus {
    NEW,
    PAID,
    CANCELLED
}

record CreateOrderRequest(
        @NotBlank
        @Size(max = 100)
        String customerName
) {}

record ApiError(String code, String message) {}

class OrderNotFoundException extends RuntimeException {
    OrderNotFoundException(long id) {
        super("Order " + id + " was not found");
    }
}

@RestController
class OrderController {

    @GetMapping("/orders")
    Map<String, String> findByStatus(
            @RequestParam OrderStatus status) {

        return Map.of("status", status.name());
    }

    @GetMapping("/orders/{id}")
    Map<String, Long> findById(@PathVariable long id) {
        if (id == 404) {
            throw new OrderNotFoundException(id);
        }
        return Map.of("id", id);
    }

    @PostMapping("/orders")
    ResponseEntity<Map<String, String>> create(
            @Valid @RequestBody CreateOrderRequest request) {

        return ResponseEntity
                .status(HttpStatus.CREATED)
                .body(Map.of("customerName", request.customerName()));
    }
}
~~~

### 8.2. Advice and Converter

~~~java
@RestControllerAdvice
class ApiExceptionHandler {

    @ExceptionHandler(OrderNotFoundException.class)
    ResponseEntity<ApiError> handleNotFound(
            OrderNotFoundException exception) {

        return ResponseEntity
                .status(HttpStatus.NOT_FOUND)
                .body(new ApiError(
                        "ORDER_NOT_FOUND",
                        exception.getMessage()
                ));
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    ResponseEntity<ApiError> handleValidation(
            MethodArgumentNotValidException exception) {

        String detail = exception.getBindingResult()
                .getFieldErrors()
                .stream()
                .map(error -> error.getField() + ": "
                        + error.getDefaultMessage())
                .findFirst()
                .orElse("Invalid request");

        return ResponseEntity.badRequest()
                .body(new ApiError("VALIDATION_FAILED", detail));
    }
}

final class StringToOrderStatusConverter
        implements Converter<String, OrderStatus> {

    @Override
    public OrderStatus convert(String source) {
        return OrderStatus.valueOf(
                source.trim().toUpperCase(Locale.ROOT)
        );
    }
}
~~~

### 8.3. Creating MockMvc and Registering Components

~~~java
class OrderControllerMockMvcTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        LocalValidatorFactoryBean validator =
                new LocalValidatorFactoryBean();
        validator.afterPropertiesSet();

        DefaultFormattingConversionService conversionService =
                new DefaultFormattingConversionService();
        conversionService.addConverter(
                new StringToOrderStatusConverter()
        );

        MappingJackson2HttpMessageConverter jsonConverter =
                new MappingJackson2HttpMessageConverter();

        mockMvc = MockMvcBuilders
                .standaloneSetup(new OrderController())
                .setControllerAdvice(new ApiExceptionHandler())
                .setMessageConverters(jsonConverter)
                .setConversionService(conversionService)
                .setValidator(validator)
                .build();
    }

    @Test
    void convertsQueryParameter() throws Exception {
        mockMvc.perform(get("/orders").param("status", "paid"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("PAID"));
    }

    @Test
    void handlesControllerException() throws Exception {
        mockMvc.perform(get("/orders/404"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code")
                        .value("ORDER_NOT_FOUND"));
    }

    @Test
    void validatesJsonRequest() throws Exception {
        mockMvc.perform(post("/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "customerName": ""
                                }
                                """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("VALIDATION_FAILED"));
    }

    @Test
    void acceptsValidJsonRequest() throws Exception {
        mockMvc.perform(post("/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .accept(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "customerName": "An"
                                }
                                """))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.customerName").value("An"));
    }
}
~~~

The example uses setMessageConverters with a single Jackson converter because the illustrated endpoints only exchange JSON. If a controller needs String, multipart, XML, or other body types, include the appropriate converters. In real projects, you can reuse the ObjectMapper and validator configured for the application to avoid tests using different serialization rules than production.

This test demonstrates component registration in the standalone builder. It does not prove that the WebMvcConfigurer configuration in the application context is correct. To verify the context configuration, use webAppContextSetup and register the beans via MVC configuration.

## 9. Combining Components in WebApplicationContext

When you need to test how the real application registers components, MVC configuration can be centralized in WebMvcConfigurer:

~~~java
@Configuration
@EnableWebMvc
@ComponentScan(basePackageClasses = {
        OrderController.class,
        ApiExceptionHandler.class
})
class MvcTestConfig implements WebMvcConfigurer {

    @Bean
    LocalValidatorFactoryBean mvcValidator() {
        return new LocalValidatorFactoryBean();
    }

    @Override
    public Validator getValidator() {
        return mvcValidator();
    }

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(
                new StringToOrderStatusConverter()
        );
    }
}
~~~

If there is a custom HTTP converter, add it via extendMessageConverters to keep default converters:

~~~java
@Override
public void extendMessageConverters(
        List<HttpMessageConverter<?>> converters) {

    converters.add(0, new CustomReportMessageConverter());
}
~~~

Test using the context:

~~~java
@ExtendWith(SpringExtension.class)
@WebAppConfiguration
@ContextConfiguration(classes = MvcTestConfig.class)
class OrderControllerWebMvcTest {

    @Autowired
    WebApplicationContext webApplicationContext;

    private MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        mockMvc = MockMvcBuilders
                .webAppContextSetup(webApplicationContext)
                .build();
    }

    @Test
    void usesMvcConfiguredConverterAndAdvice() throws Exception {
        mockMvc.perform(get("/orders").param("status", "paid"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("PAID"));
    }
}
~~~

In this example:

- Component scan registers the controller and advice as beans.
- addFormatters adds the converter to MVC's conversion service.
- getValidator provides the validator for the MVC infrastructure.
- Custom HTTP converters are added via extendMessageConverters.
- webAppContextSetup uses the components configured in the context.

@EnableWebMvc enables Spring MVC configuration. If the application uses Spring Boot, auto-configuration may be responsible for the MVC infrastructure; do not add @EnableWebMvc arbitrarily because this annotation switches the application to explicit MVC configuration and may alter some auto-configuration behaviors. With Spring Boot test slices such as @WebMvcTest, check which beans and configurations are included in the slice rather than assuming the entire application context is loaded.

## 10. Common Registration Errors

### Advice Does Not Handle the Exception

Check:

- Did the standalone builder call setControllerAdvice?
- Is the advice a bean in WebApplicationContext?
- Does component scan cover the advice's package?
- Does the advice's selector exclude the controller under test?
- Is a controller-level handler or higher-order advice handling the exception first?
- Does the actual exception match the exact type or cause relationship declared by the handler?

If the response is still HTTP 500, inspect the root exception and the HandlerExceptionResolvers involved.

### Custom Converter Is Not Invoked

Identify which layer is converting the data:

- JSON body: check HttpMessageConverter.
- Query parameter, path variable, or form field: check ConversionService, Converter, or Formatter.

Then verify the converter is registered in the right builder/context and that its source and target types match the handler method.

### JSON Converter Is Missing After Configuration

In standalone mode, setMessageConverters takes the converter list provided by the test. If you only add a custom converter, default converters may no longer be in the list. Supply all needed converters or switch to webAppContextSetup to use the MVC configuration.

In WebMvcConfigurer, use extendMessageConverters when adding converters while retaining the default list.

### Validator Does Not Run

Check:

- Does the DTO have the proper validation annotations?
- Does the handler parameter have @Valid or @Validated where needed?
- Is a Bean Validation provider on the classpath?
- Did the standalone builder call setValidator?
- Does the MVC context have an appropriate validator?
- Did the request body deserialize successfully before validation began?

If JSON is malformed or fails to deserialize, the error may occur before the Bean Validation step.

### Test Receives the Right Status Code but Wrong Response Body

A correct status code does not guarantee the response body matches the contract. Also verify content type, key JSON fields, and stable error codes. Avoid comparing the entire JSON string if property ordering is not part of the contract.

### Standalone Test Passes but Real Application Fails

Standalone setup uses only the configuration passed to the builder and its defaults. It does not automatically reflect every WebMvcConfigurer, advice bean, validator, or converter in the application. When an error occurs only in the integration environment, create a webAppContextSetup test to verify the actual MVC configuration.

## 11. Choosing Test Scope

Tests can be divided by goal:

| Goal | Suitable Setup | Components to Verify |
|---|---|---|
| A single controller handles business errors | standaloneSetup | ControllerAdvice and error response |
| Binding query/path parameters | standaloneSetup or webAppContextSetup | Converter/Formatter |
| JSON request/response | Both | HttpMessageConverter |
| Bean Validation of request DTO | Both | Validator and @Valid |
| Application MVC configuration | webAppContextSetup | Advice, converters, conversion service, and validator registered in the context |
| Interaction across multiple controllers and MVC configuration | webAppContextSetup | Request flow through MVC infrastructure |

Not every controller test needs to start the entire application context. Small tests pinpoint specific behaviors; context integration tests confirm components are wired properly in the application configuration.

When multiple tests share the same standalone setup, you can create a shared factory or test configuration for a similar group of controllers. However, keep registered components explicit so readers know which configuration the test simulates.

## 12. Practical Guidelines

1. Distinguish HttpMessageConverter from Converter and Formatter before configuring.
2. With standaloneSetup, explicitly register the advice, message converters, conversion service, and validator that the test needs.
3. With webAppContextSetup, let the Spring context manage MVC components and verify the actual application configuration.
4. Use extendMessageConverters when you want to add converters while preserving the default list.
5. Use addFormatters to register converters/formatters for data binding.
6. Use getValidator or setValidator depending on the MockMvc setup style in use.
7. Place @Valid or @Validated in the right positions to trigger validation.
8. Test requests and responses through MockMvc to prove components actually participate in processing.
9. Assert status, content type, and key response fields, especially when advice standardizes errors.
10. Do not infer that a standalone test verifies the entire MVC configuration in the application context.

A reliable MockMvc test must craft requests that pass through the exact components the test scope aims to verify. ControllerAdvice determines how errors become HTTP responses; converters determine how data crosses the HTTP/Java type boundary; validators ensure data satisfies rules before business logic executes. Registering these three component groups properly makes tests clearly reflect actual Spring MVC behavior and catch configuration errors early in development.

