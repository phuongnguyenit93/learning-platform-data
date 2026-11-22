# Kiểm thử SDK bằng mock, endpoint tùy chỉnh và tài khoản thử nghiệm

> **Chương:** AWS SDK cho Java  
> **Học phần:** `CLOUD_PROVIDERS_AWS` — khám phá hệ sinh thái AWS qua Region/AZ, IAM, VPC, dịch vụ tính toán, lưu trữ, cơ sở dữ liệu, tích hợp và serverless; rèn khả năng chọn dịch vụ, thiết kế và triển khai ứng dụng an toàn, có giám sát, phục hồi và kiểm soát chi phí.

Một service Java nhận yêu cầu tải ảnh sản phẩm lên **Amazon S3**, ghi metadata vào **DynamoDB** rồi gửi message tới **Amazon SQS**. Nếu mỗi lần chạy unit test đều gọi AWS thật, bài test phụ thuộc Internet, IAM, account quota, trạng thái tài nguyên và chi phí. Một lỗi nhỏ trong code có thể tạo bucket hoặc message thật; test chạy lại có thể để lại tài nguyên rác.

**AWS SDK for Java 2.x** cung cấp client cho các dịch vụ AWS, đồng thời cho phép kiểm thử ở nhiều mức:

- **Mock client:** kiểm tra logic ứng dụng, không tạo HTTP request.
- **HTTP stub + endpoint tùy chỉnh:** kiểm tra serialization, protocol request, SigV4 signing và xử lý response mà không gọi AWS.
- **Local emulator/container:** kiểm tra tích hợp service trong môi trường phát triển có thể tái tạo.
- **AWS sandbox/test account:** kiểm chứng hành vi thật của IAM, networking, quotas và dịch vụ AWS.

Không một mức test nào thay thế hoàn toàn các mức còn lại. Mock có thể xác nhận code gọi `putObject` đúng tham số nhưng không chứng minh request được ký đúng; HTTP stub có thể kiểm tra request nhưng không chứng minh IAM policy cho phép; LocalStack có thể mô phỏng nhiều API nhưng không thay thế một lần integration test trên AWS thật.

Bài này sử dụng **AWS SDK for Java 2.x**, JUnit 5 và ví dụ S3/DynamoDB/SQS. Các dependency version được quản lý tập trung theo dự án; hãy chọn phiên bản SDK v2, JUnit, Mockito, WireMock và Testcontainers đã được kiểm tra với build hiện tại.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Chọn đúng cấp độ test: mock, HTTP stub, LocalStack/Testcontainers hay AWS test account.
2. Mock AWS service clients bằng Mockito và xác minh request/response/error behavior.
3. Tạo client với `endpointOverride`, Region và test credentials để gửi request tới HTTP stub.
4. Kiểm tra AWS Signature Version 4 (SigV4) ở mức request mà không dùng credentials thật.
5. Chạy integration tests với LocalStack/Testcontainers và hiểu giới hạn của emulator.
6. Thiết lập AWS sandbox account, role, profile, region và account guard trước khi chạy test thật.
7. Tạo tài nguyên test có tên riêng, cleanup an toàn, giới hạn chi phí và tránh tác động production.
8. Kiểm thử retry, timeout, pagination, async clients, error handling và client lifecycle.
9. Tích hợp test vào CI/CD mà không lưu access keys dài hạn trong repository.

## 2. Test pyramid cho AWS SDK

~~~mermaid
flowchart TB
    E2E["AWS sandbox integration tests\nÍt hơn, chạy có kiểm soát"]
    LOCAL["LocalStack / Testcontainers\nService integration locally"]
    HTTP["HTTP stub / WireMock\nEndpoint override + protocol"]
    UNIT["Unit tests / Mockito\nBusiness logic and interactions"]
    E2E --> LOCAL
    LOCAL --> HTTP
    HTTP --> UNIT
~~~

Mỗi tầng trả lời một loại câu hỏi:

| Tầng | Câu hỏi | Có gọi AWS thật? | Chi phí/tốc độ |
| --- | --- | --- | --- |
| **Unit + mock client** | Service có gọi SDK đúng khi success/failure? | Không | Nhanh, chi phí thấp |
| **HTTP stub** | SDK gửi HTTP request, headers, body và parse response thế nào? | Không | Nhanh, kiểm soát cao |
| **LocalStack/Testcontainers** | Nhiều thành phần có phối hợp qua API gần AWS không? | Không gọi AWS, chạy emulator | Cần Docker/tài nguyên local |
| **AWS test account** | IAM, endpoint, quota, service semantics và networking thật có đúng? | Có | Chậm hơn, có thể phát sinh phí |

**Quy tắc thực tế:** phần lớn business rules nên được kiểm tra bằng unit tests; dùng HTTP stubs cho các trường hợp cần kiểm tra giao thức; dùng emulator cho luồng tích hợp phù hợp; giữ AWS sandbox tests cho những hành vi chỉ AWS thật mới xác nhận được.

### 2.1. Khi nào không nên mock SDK?

Nếu test chỉ xác nhận `verify(s3Client).putObject(...)`, nó chưa kiểm tra:

- SDK build đúng HTTP request hay không.
- Request được ký bằng Region/service name phù hợp hay không.
- JSON/headers được serialize đúng hay không.
- Response hoặc error body được parse thành SDK exception ra sao.
- Endpoint tùy chỉnh, TLS và retry policy có hoạt động hay không.

Khi những yếu tố này quan trọng, hãy thêm HTTP stub hoặc integration test.

### 2.2. Khi nào không nên gọi AWS thật?

Không dùng AWS sandbox cho từng unit test hoặc test cần chạy hàng trăm lần mỗi commit. Các test này sẽ phụ thuộc IAM, account quota, network, service availability, eventual consistency và có thể tạo chi phí. Chỉ chạy AWS integration tests trong stage riêng với tài nguyên có lifecycle rõ ràng.

## 3. Chuẩn bị dependency cho AWS SDK for Java 2.x

Nên dùng **AWS SDK BOM** để đồng bộ version giữa các module. Ví dụ Maven dưới đây minh họa cấu trúc dependency; thay **YOUR_APPROVED_SDK_V2_VERSION** bằng version v2 đã được dự án chọn và quản lý qua parent/POM.

~~~xml
<dependencyManagement>
  <dependencies>
    <dependency>
      <groupId>software.amazon.awssdk</groupId>
      <artifactId>bom</artifactId>
      <version>YOUR_APPROVED_SDK_V2_VERSION</version>
      <type>pom</type>
      <scope>import</scope>
    </dependency>
  </dependencies>
</dependencyManagement>

<dependencies>
  <dependency>
    <groupId>software.amazon.awssdk</groupId>
    <artifactId>s3</artifactId>
  </dependency>
  <dependency>
    <groupId>software.amazon.awssdk</groupId>
    <artifactId>dynamodb</artifactId>
  </dependency>
  <dependency>
    <groupId>software.amazon.awssdk</groupId>
    <artifactId>sqs</artifactId>
  </dependency>
  <dependency>
    <groupId>software.amazon.awssdk</groupId>
    <artifactId>sts</artifactId>
  </dependency>
</dependencies>
~~~

Dependencies test thường gồm:

- `org.junit.jupiter:junit-jupiter`
- `org.mockito:mockito-junit-jupiter`
- `com.github.tomakehurst:wiremock-standalone`
- `org.testcontainers:junit-jupiter`
- `org.testcontainers:localstack`

Chỉ thêm những thư viện cần dùng. Nếu project đã dùng Spring Boot dependency management, kiểm tra version do parent quản lý trước khi thêm BOM thứ hai để tránh dependency convergence conflict.

### 3.1. Chọn AWS SDK v2

Ví dụ trong bài dùng client v2 như:

~~~java
S3Client s3 = S3Client.builder()
    .region(Region.AP_SOUTHEAST_1)
    .build();
~~~

SDK v2 dùng immutable request/response models và builder API. **Sync clients** như `S3Client` và `DynamoDbClient` thường được dùng trong các service đồng bộ; **async clients** như `S3AsyncClient` trả `CompletableFuture` và cần test completion/error paths riêng.

Không trộn import `com.amazonaws...` của SDK v1 với `software.amazon.awssdk...` của SDK v2 trong cùng ví dụ. Nếu dự án vẫn còn SDK v1, nên có kế hoạch migration và kiểm thử tương ứng riêng.

## 4. Mock service client bằng Mockito

AWS SDK v2 service clients là interface, ví dụ `S3Client`, `DynamoDbClient`, `SqsClient`. Mockito có thể thay client bằng mock để test business logic mà không cần network.

### 4.1. Service cần kiểm thử

~~~java
public final class ProductImageService {
    private final S3Client s3;
    private final String bucket;

    public ProductImageService(S3Client s3, String bucket) {
        this.s3 = s3;
        this.bucket = bucket;
    }

    public String upload(String key, byte[] bytes) {
        PutObjectResponse response = s3.putObject(
            PutObjectRequest.builder()
                .bucket(bucket)
                .key(key)
                .contentType("image/png")
                .build(),
            RequestBody.fromBytes(bytes)
        );
        return response.eTag();
    }
}
~~~

Đây là service tối giản để minh họa. Ứng dụng thực tế có thể cần validate key, giới hạn kích thước, metadata, checksum, encryption và xử lý idempotency.

### 4.2. Test success và verify request

~~~java
@ExtendWith(MockitoExtension.class)
class ProductImageServiceTest {
    @Mock
    S3Client s3;

    @Test
    void uploadsImageToExpectedBucketAndKey() {
        when(s3.putObject(
            any(PutObjectRequest.class),
            any(RequestBody.class)
        )).thenReturn(
            PutObjectResponse.builder().eTag("test-etag").build()
        );

        ProductImageService service =
            new ProductImageService(s3, "test-images");

        String etag = service.upload("products/42.png",
            new byte[] {1, 2, 3});

        assertEquals("test-etag", etag);

        ArgumentCaptor<PutObjectRequest> request =
            ArgumentCaptor.forClass(PutObjectRequest.class);
        verify(s3).putObject(request.capture(), any(RequestBody.class));

        assertEquals("test-images", request.getValue().bucket());
        assertEquals("products/42.png", request.getValue().key());
        assertEquals("image/png", request.getValue().contentType());
    }
}
~~~

Imports Mockito/JUnit và static matchers/assertions được lược bớt để tập trung vào test. `RequestBody` là request body abstraction của SDK v2; nếu cần xác minh bytes chính xác, kiểm tra dữ liệu đầu vào ở tầng adapter riêng hoặc dùng HTTP stub để kiểm tra request body thật.

### 4.3. Test error path

~~~java
@Test
void propagatesAccessDeniedFromS3() {
    when(s3.putObject(
        any(PutObjectRequest.class),
        any(RequestBody.class)
    )).thenThrow(
        S3Exception.builder()
            .statusCode(403)
            .message("AccessDenied")
            .build()
    );

    ProductImageService service =
        new ProductImageService(s3, "test-images");

    assertThrows(S3Exception.class,
        () -> service.upload("products/42.png", new byte[] {1}));
}
~~~

Test này xác nhận service truyền exception ra caller. Nếu application có exception translation/retry policy, test behavior đó ở application boundary: ví dụ 403 không retry, throttling có retry theo policy, validation error trả lỗi nghiệp vụ phù hợp.

### 4.4. Mock không nên kiểm tra implementation detail quá sâu

Tránh verify mọi getter, mọi builder call hoặc thứ tự những tương tác không phải contract. Một test nên xác nhận **kết quả nghiệp vụ và những interaction có ý nghĩa**. Nếu test quá phụ thuộc chi tiết cách SDK được gọi, refactor nhỏ cũng làm test hỏng dù behavior không đổi.

## 5. HTTP stub: kiểm tra SDK request mà không gọi AWS

Mock client bỏ qua HTTP pipeline của SDK. **WireMock** có thể dựng HTTP server cục bộ để kiểm tra request do AWS SDK v2 thật sự gửi.

~~~mermaid
sequenceDiagram
    participant T as JUnit test
    participant SDK as AWS SDK v2 client
    participant W as WireMock server
    T->>W: Start local HTTP server
    T->>SDK: Build client with local endpoint and test credentials
    T->>SDK: putObject(...)
    SDK->>W: Signed HTTP request
    W-->>SDK: Stubbed HTTP response
    SDK-->>T: SDK response model
    T->>W: Verify path, headers and body
~~~

### 5.1. Dựng S3 client với endpoint tùy chỉnh

~~~java
WireMockServer wireMock = new WireMockServer(options().dynamicPort());
wireMock.start();

S3Client s3 = S3Client.builder()
    .region(Region.US_EAST_1)
    .endpointOverride(URI.create(wireMock.baseUrl()))
    .credentialsProvider(
        StaticCredentialsProvider.create(
            AwsBasicCredentials.create(
                "test-access-key",
                "test-secret-key"
            )
        )
    )
    .serviceConfiguration(
        S3Configuration.builder()
            .pathStyleAccessEnabled(true)
            .build()
    )
    .build();
~~~

Các credential trên là **giá trị giả chỉ để ký request tới server cục bộ**. SDK vẫn cần Region để tạo SigV4 signing scope dù endpoint không phải AWS. `endpointOverride` thay địa chỉ dịch vụ; nó không tự tắt signing.

`pathStyleAccessEnabled(true)` hữu ích với một số S3-compatible test servers vì request có dạng `/bucket/key`. Đây là cấu hình phục vụ test endpoint; không áp dụng tùy tiện cho endpoint S3 production nếu không phù hợp yêu cầu dịch vụ.

### 5.2. Stub PUT và xác minh SigV4 header

~~~java
stubFor(put(urlEqualTo("/test-images/products/42.png"))
    .willReturn(aResponse()
        .withStatus(200)
        .withHeader("ETag", "\"wiremock-etag\"")));

try (S3Client s3 = buildS3Client(wireMock.baseUrl())) {
    PutObjectResponse response = s3.putObject(
        PutObjectRequest.builder()
            .bucket("test-images")
            .key("products/42.png")
            .contentType("image/png")
            .build(),
        RequestBody.fromBytes(new byte[] {1, 2, 3})
    );

    assertEquals("\"wiremock-etag\"", response.eTag());
}

verify(putRequestedFor(
    urlEqualTo("/test-images/products/42.png")
).withHeader(
    "Authorization",
    matching("AWS4-HMAC-SHA256.*")
));
~~~

Ví dụ giả định `buildS3Client` tạo client theo mục 5.1 và WireMock đã chạy. WireMock có thể kiểm tra request path, headers, query parameters và body; test nên xác nhận thêm các header nghiệp vụ quan trọng nếu ứng dụng phụ thuộc vào chúng.

**Không assert toàn bộ Authorization signature là một chuỗi cố định** nếu timestamp, payload hash hoặc signing behavior thay đổi. Assert scheme/credential scope ở mức phù hợp; kiểm tra signature cryptographic đầy đủ chỉ khi test harness có verifier SigV4 chuyên dụng.

### 5.3. Đóng server và client đúng cách

~~~java
@AfterEach
void tearDown() {
    if (s3 != null) {
        s3.close();
    }
    if (wireMock != null) {
        wireMock.stop();
    }
}
~~~

Trong test suite thật, nên dùng JUnit extension hoặc `try/finally` để cleanup ngay cả khi assertion thất bại. Nếu tạo server/client ở `@BeforeAll`, cần quản lý lifecycle tương ứng với `@AfterAll`; không để port hoặc thread tồn tại giữa các test run.

## 6. Endpoint tùy chỉnh, Region và credentials

### 6.1. Ba cấu hình cần có khi dùng endpointOverride

Một client test endpoint thường cần:

1. **Endpoint URI:** địa chỉ HTTP/HTTPS của WireMock, LocalStack hoặc service emulator.
2. **Region:** Region được dùng trong signing scope; endpoint local không làm Region biến mất.
3. **Credentials provider:** credential giả hoặc provider thử nghiệm; SDK cần credentials để ký request nếu signer được bật.

Ví dụ:

~~~java
AwsCredentialsProvider testCredentials =
    StaticCredentialsProvider.create(
        AwsBasicCredentials.create("test-key", "test-secret")
    );

DynamoDbClient dynamo = DynamoDbClient.builder()
    .endpointOverride(URI.create("http://localhost:4566"))
    .region(Region.AP_SOUTHEAST_1)
    .credentialsProvider(testCredentials)
    .build();
~~~

Đây là cấu hình thường dùng cho local emulator có endpoint cố định. Với WireMock, nên dùng dynamic port và truyền URI thực của server đang chạy. **Không dùng test credentials này với AWS endpoint thật**; chúng không phải IAM credentials hợp lệ.

### 6.2. Endpoint override không tự đổi mọi cấu hình mạng

`endpointOverride` đặt base URI cho service client. Ứng dụng vẫn phải quan tâm:

- Scheme HTTP/HTTPS và TLS truststore.
- Path-style hay virtual-host-style addressing, đặc biệt với S3-compatible endpoints.
- Region/signing region mà endpoint giả lập mong đợi.
- Proxy, DNS, connection timeout và socket timeout.
- Service-specific endpoint rules và client configuration.

Không dùng endpoint local trong production config. Nên tách profile cấu hình hoặc dependency injection rõ ràng để test endpoint không thể bị bật nhầm ở môi trường thật.

### 6.3. Dùng test credentials an toàn

- Dùng fake credentials trong WireMock/LocalStack tests.
- Với AWS sandbox, dùng IAM role/SSO/assume-role hoặc CI workload identity.
- Không commit access key/secret key vào Git, `.env` mẫu có giá trị thật, test reports hoặc logs.
- Không bật `StaticCredentialsProvider` với credentials thật chỉ để làm test “dễ chạy”.
- Tránh in toàn bộ request Authorization header vì nó chứa credential scope và chữ ký.

## 7. Kiểm tra DynamoDB protocol bằng HTTP stub

DynamoDB sử dụng JSON protocol qua HTTP POST; SDK tạo header target để định danh operation. WireMock có thể xác minh payload và trả response giả.

~~~java
stubFor(post(urlEqualTo("/"))
    .withHeader("X-Amz-Target",
        equalTo("DynamoDB_20120810.GetItem"))
    .willReturn(aResponse()
        .withStatus(200)
        .withHeader("Content-Type", "application/x-amz-json-1.0")
        .withBody("""
            {
              "Item": {
                "pk": {"S": "PRODUCT#42"},
                "name": {"S": "Keyboard"}
              }
            }
            """)));

try (DynamoDbClient client = DynamoDbClient.builder()
        .endpointOverride(URI.create(wireMock.baseUrl()))
        .region(Region.US_EAST_1)
        .credentialsProvider(testCredentials)
        .build()) {

    GetItemResponse response = client.getItem(GetItemRequest.builder()
        .tableName("catalog-test")
        .key(Map.of("pk", AttributeValue.builder()
            .s("PRODUCT#42")
            .build()))
        .build());

    assertEquals("Keyboard",
        response.item().get("name").s());
}
~~~

Đoạn JSON text block yêu cầu Java 15 trở lên; nếu project dùng Java 11, thay bằng string literal ghép dòng hoặc resource file. Test cần stub đúng protocol headers và response format của operation; một response JSON hợp lệ cho API khác không đủ.

### 7.1. Test lỗi service

Có thể trả HTTP 400/500 cùng error headers/body tương ứng để kiểm tra SDK tạo `DynamoDbException`, mã lỗi và retry behavior. AWS JSON protocol có cấu trúc error response riêng; tham khảo response thực tế trong tài liệu service/API và tránh giả định mọi dịch vụ trả error body giống nhau.

## 8. Những điều HTTP stub xác minh được và không xác minh được

| Có thể kiểm tra | Không thể chứng minh chỉ bằng stub |
| --- | --- |
| HTTP method, path, query, headers | IAM policy thực sự cho phép thao tác |
| Request serialization và response parsing | Service quota/account limits |
| SigV4 header có được tạo | Chữ ký được AWS chấp nhận cho đúng credential/clock |
| SDK xử lý status/error code | Semantics đầy đủ của AWS service |
| Retry request trong kịch bản stubbed | Retry/throttling behavior chính xác của production AWS |
| Endpoint override và Region trong client config | DNS, VPC, Security Group, PrivateLink thực tế |

WireMock là **HTTP contract test**, không phải AWS simulator đầy đủ. Dùng LocalStack hoặc sandbox account khi cần kiểm tra thêm service behavior.

## 9. LocalStack và Testcontainers

**LocalStack** mô phỏng nhiều AWS APIs để phát triển và kiểm tra tích hợp trên máy hoặc CI. **Testcontainers** quản lý vòng đời container theo test suite, giúp môi trường test có thể tái tạo và tự cleanup.

~~~mermaid
flowchart LR
    J["JUnit 5 test"] --> TC["Testcontainers"]
    TC --> LS["LocalStack container"]
    J --> SDK["AWS SDK v2 client"]
    SDK -->|"endpointOverride"| LS
    LS --> S3["S3 API"]
    LS --> DDB["DynamoDB API"]
    LS --> SQS["SQS API"]
~~~

### 9.1. Khởi tạo LocalStack container

~~~java
@Testcontainers
class S3LocalStackIntegrationTest {
    @Container
    static final LocalStackContainer localStack =
        new LocalStackContainer(
            DockerImageName.parse("localstack/localstack:3.8.1")
        ).withServices(LocalStackContainer.Service.S3);

    @Test
    void uploadsAndReadsObject() {
        AwsCredentialsProvider credentials =
            StaticCredentialsProvider.create(
                AwsBasicCredentials.create(
                    localStack.getAccessKey(),
                    localStack.getSecretKey()
                )
            );

        try (S3Client s3 = S3Client.builder()
                .endpointOverride(localStack.getEndpointOverride(
                    LocalStackContainer.Service.S3))
                .region(Region.of(localStack.getRegion()))
                .credentialsProvider(credentials)
                .serviceConfiguration(
                    S3Configuration.builder()
                        .pathStyleAccessEnabled(true)
                        .build()
                )
                .build()) {

            String bucket = "it-" +
                UUID.randomUUID().toString().replace("-", "");
            String key = "sample.txt";
            byte[] expected = "hello from test".getBytes(
                StandardCharsets.UTF_8);

            s3.createBucket(CreateBucketRequest.builder()
                .bucket(bucket)
                .build());

            try {
                s3.putObject(PutObjectRequest.builder()
                        .bucket(bucket)
                        .key(key)
                        .build(),
                    RequestBody.fromBytes(expected));

                byte[] actual = s3.getObjectAsBytes(
                    GetObjectRequest.builder()
                        .bucket(bucket)
                        .key(key)
                        .build()
                ).asByteArray();

                assertArrayEquals(expected, actual);
            } `finally` {
                s3.deleteObject(DeleteObjectRequest.builder()
                    .bucket(bucket)
                    .key(key)
                    .build());
                s3.deleteBucket(DeleteBucketRequest.builder()
                    .bucket(bucket)
                    .build());
            }
        }
    }
}
~~~

Đây là ví dụ minh họa API Testcontainers LocalStack module; imports được lược bớt. Hãy pin image version đã được tổ chức kiểm thử thay vì dùng tag thay đổi theo thời gian, và kiểm tra API tương ứng với version Testcontainers trong dự án. Bucket được tạo riêng cho test và xóa trong khối `finally`.

### 9.2. LocalStack xác minh được gì?

- Nhiều service API flows có thể chạy mà không cần AWS account.
- SDK endpoint override, request serialization và client wiring hoạt động với endpoint giả lập.
- Test có thể tạo, đọc, cập nhật và xóa tài nguyên trong môi trường cô lập.
- CI có thể chạy integration tests mà không cấp AWS production credentials.

### 9.3. LocalStack không thay thế AWS thật

LocalStack là emulator, không phải AWS Region. Một số API, IAM semantics, service limits, eventual consistency, event delivery, networking, encryption/KMS, performance và edge cases có thể khác AWS. **Test pass trên LocalStack không chứng minh production IAM/network/service configuration đúng.**

Dùng AWS sandbox cho những behavior mà emulator không mô phỏng đầy đủ hoặc có ảnh hưởng đến quyết định production.

### 9.4. Dùng Testcontainers có kỷ luật

- Pin image version và kiểm tra image source.
- Không chia sẻ container state giữa test cases nếu test cần isolation.
- Dùng dynamic host ports; không giả định port local cố định ngoài cấu hình container.
- Chờ service health/readiness trước khi tạo client.
- Đóng SDK clients và để Testcontainers dừng container sau suite.
- Tách integration tests khỏi unit test task nếu Docker không có trên mọi developer machine.

## 10. AWS sandbox/test account: kiểm tra hành vi thật

Một **sandbox account** là AWS account dành cho development/integration testing, tách biệt production và có quyền/tài nguyên giới hạn. Nó giúp kiểm chứng những điều mock và emulator không thể chứng minh:

- IAM role/policy và resource-based policies.
- Region availability, service endpoints và networking thật.
- Quotas, throttling và service-specific semantics.
- Eventual consistency, retries, pagination và lifecycle thật.
- KMS, encryption, VPC endpoints, DNS và cross-service permissions.

### 10.1. Nguyên tắc account isolation

Trước khi chạy:

1. Chỉ định rõ **AWS test account ID** và allowed Regions.
2. Dùng role riêng cho test, quyền tối thiểu theo tài nguyên/prefix.
3. Cấu hình budget, billing alerts và quota phù hợp.
4. Không cho test role assume production roles hoặc truy cập production data.
5. Bật CloudTrail và lưu change/run ID để truy vết.
6. Dùng dữ liệu giả hoặc đã được phê duyệt; không copy PII/secret vào sandbox tùy tiện.

Một account có tên **sandbox** không tự động an toàn. **Account ID, role trust, SCP, IAM policies, network boundary và dữ liệu** mới xác định ranh giới thật.

### 10.2. Credentials cho local development

Có thể sử dụng AWS CLI profile đã được thiết lập qua SSO hoặc cơ chế tổ chức phê duyệt:

~~~bash
aws sso login --profile aws-sdk-test
aws sts get-caller-identity --profile aws-sdk-test
~~~

Chạy test với profile được chỉ định:

~~~bash
AWS_PROFILE=aws-sdk-test AWS_REGION=ap-southeast-1 \
  mvn -Paws-integration verify
~~~

Ví dụ shell dùng cú pháp POSIX; trên Windows PowerShell có thể đặt biến môi trường theo cú pháp của shell. Profile cần được cấu hình trước trong AWS CLI, không lưu credential vào file project.

Trong CI, ưu tiên **OIDC/workload identity hoặc assume-role với session ngắn hạn** thay cho access keys dài hạn. Không đặt access key/secret key trong repository, Docker image hoặc pipeline logs.

### 10.3. Account guard bằng STS

Trước khi tạo bất kỳ resource nào, kiểm tra caller identity và từ chối chạy nếu account không đúng:

~~~java
public final class AwsTestAccountGuard {
    private AwsTestAccountGuard() {}

    public static void requireExpectedAccount(
            StsClient sts,
            String expectedAccountId) {

        if (expectedAccountId == null ||
                !expectedAccountId.matches("[0-9]{12}")) {
            throw new IllegalStateException(
                "AWS_TEST_ACCOUNT_ID must be a 12-digit account ID");
        }

        String actualAccountId =
            sts.getCallerIdentity().account();

        if (!expectedAccountId.equals(actualAccountId)) {
            throw new IllegalStateException(
                "Refusing AWS integration test in unexpected account");
        }
    }
}
~~~

Test nên gọi guard ngay khi bắt đầu setup. Không log access key, secret, session token hoặc toàn bộ caller identity nếu không cần thiết. Account guard là **safety check bổ sung**; IAM/SCP vẫn phải chặn các hành động không được phép.

### 10.4. Tạo clients cho test account

~~~java
Region region = Region.of(
    System.getenv().getOrDefault("AWS_REGION", "ap-southeast-1")
);

AwsCredentialsProvider credentials =
    ProfileCredentialsProvider.create("aws-sdk-test");

try (StsClient sts = StsClient.builder()
        .region(region)
        .credentialsProvider(credentials)
        .build()) {
    AwsTestAccountGuard.requireExpectedAccount(
        sts, System.getenv("AWS_TEST_ACCOUNT_ID"));
}

S3Client s3 = S3Client.builder()
    .region(region)
    .credentialsProvider(credentials)
    .build();
~~~

Trong CI, thay profile provider bằng provider phù hợp với role/session của pipeline. SDK clients nên được inject vào test fixture và đóng sau khi test suite hoàn tất.

## 11. Tài nguyên test: tên riêng, cleanup và chi phí

### 11.1. Mỗi test run cần namespace riêng

Không dùng bucket/table/queue tên cố định cho nhiều test jobs chạy song song. Tạo suffix ngẫu nhiên hoặc run ID:

~~~java
String runId = UUID.randomUUID()
    .toString()
    .replace("-", "")
    .substring(0, 12);

String bucketName = "sdk-it-" + runId;
String tableName = "sdk-it-catalog-" + runId;
String queueName = "sdk-it-events-" + runId;
~~~

S3 bucket name phải tuân theo quy tắc global naming và không chứa ký tự viết hoa; kiểm tra naming constraints của từng service. Với DynamoDB/SQS, áp dụng giới hạn độ dài và ký tự hợp lệ của tên resource.

### 11.2. Cleanup bằng finally

~~~java
String bucket = createTestBucket(s3);
try {
    uploadFixture(s3, bucket);
    assertObjectCanBeRead(s3, bucket);
} finally {
    deleteTestObjects(s3, bucket);
    deleteTestBucket(s3, bucket);
}
~~~

Không dựa vào `@AfterEach` duy nhất nếu test process có thể bị kill hoặc runner mất kết nối. Với sandbox account, bổ sung **resource tags**, run ID, owner và TTL/expiry tag; có scheduled janitor để phát hiện và xóa tài nguyên mồ côi theo allowlist.

### 11.3. Dọn tài nguyên theo đúng semantics

| Resource | Trước khi xóa | Lưu ý |
| --- | --- | --- |
| **S3 bucket** | Xóa objects, multipart uploads; kiểm tra versioning | Bucket versioned cần xóa object versions/delete markers |
| **DynamoDB table** | Chờ create hoàn tất; xóa table sau test | Delete là bất đồng bộ; dùng waiter nếu bước sau cần chắc chắn |
| **SQS queue** | Dừng producers/consumers, xóa queue | Xóa queue có thể ảnh hưởng message đang chờ; chỉ dùng queue riêng cho test |
| **SNS topic** | Gỡ subscriptions nếu cần, rồi delete topic | Kiểm tra subscription/resource dependencies |
| **Lambda function** | Dừng invocation và xóa function/roles test nếu tạo riêng | Kiểm tra log groups, layers và event source mappings |

### 11.4. Budget và giới hạn test

- Dùng service quota thấp/đủ dùng và giới hạn concurrency.
- Không chạy load test lớn trong sandbox mặc định.
- Giới hạn thời gian tồn tại tài nguyên và số lượng test resources.
- Theo dõi cost allocation tags và budget alerts.
- Dùng test payload nhỏ, không upload file lớn hoặc tạo hàng triệu items trừ khi có test plan riêng.
- Tách tests cần compute/network tốn kém khỏi pull request pipeline thông thường.

## 12. Kiểm thử SQS và DynamoDB ở cấp client

### 12.1. Mock SQS sendMessage

~~~java
@Test
void sendsOrderEventToConfiguredQueue() {
    when(sqs.sendMessage(any(SendMessageRequest.class)))
        .thenReturn(SendMessageResponse.builder()
            .messageId("message-test-1")
            .build());

    OrderEventPublisher publisher =
        new OrderEventPublisher(sqs, "https://sqs.test/queue/orders");

    String messageId = publisher.publish(
        new OrderCreatedEvent("order-42"));

    assertEquals("message-test-1", messageId);

    ArgumentCaptor<SendMessageRequest> request =
        ArgumentCaptor.forClass(SendMessageRequest.class);
    verify(sqs).sendMessage(request.capture());
    assertEquals("https://sqs.test/queue/orders",
        request.getValue().queueUrl());
    assertTrue(request.getValue().messageBody().contains("order-42"));
}
~~~

Ví dụ giả định `OrderEventPublisher` serialize event thành JSON. Test có thể xác minh queue URL, message body, attributes và FIFO fields (`MessageGroupId`, `MessageDeduplicationId`) nếu queue dùng FIFO.

### 12.2. Mock DynamoDB conditional write

~~~java
when(dynamo.putItem(any(PutItemRequest.class)))
    .thenReturn(PutItemResponse.builder().build());

repository.createIfAbsent("PRODUCT#42", "Keyboard");

ArgumentCaptor<PutItemRequest> request =
    ArgumentCaptor.forClass(PutItemRequest.class);
verify(dynamo).putItem(request.capture());

assertEquals("catalog-test", request.getValue().tableName());
assertEquals("attribute_not_exists(pk)",
    request.getValue().conditionExpression());
~~~

Đây là ví dụ repository contract; map attribute values và expression names cần theo schema thực tế. Ngoài success, nên test `ConditionalCheckFailedException` để bảo đảm duplicate item được xử lý như conflict nghiệp vụ, không bị coi là lỗi hệ thống retry vô hạn.

### 12.3. Test serialization riêng với AWS client

Đừng để test cache/serialization phụ thuộc vào mock SDK. Với event hoặc DynamoDB item:

- Test object → JSON/attribute map.
- Test JSON/attribute map → object.
- Test missing/unknown fields và schema version.
- Test Unicode, empty values, timestamp và numeric precision.
- Test compatibility khi application version cũ và mới cùng chạy trong rolling deployment.

Tách serialization thành component thuần Java để unit test không cần AWS client.

## 13. Pagination, waiters và eventual consistency

### 13.1. Test paginator xử lý đủ trang

SDK v2 cung cấp paginator cho nhiều operations. Ví dụ S3:

~~~java
List<S3Object> objects =
    s3.listObjectsV2Paginator(ListObjectsV2Request.builder()
            .bucket("test-images")
            .prefix("products/")
            .build())
        .contents()
        .stream()
        .toList();
~~~

Test nên có dữ liệu giả lập nhiều trang và xác minh ứng dụng không chỉ đọc trang đầu. Với HTTP stub, trả `IsTruncated=true` và `NextContinuationToken` ở trang đầu; trang tiếp theo phải được request với token đó. Với mock client, stub response sequence và xác minh lần gọi tiếp theo.

### 13.2. Waiters không phải sleep cố định

Một số AWS APIs hoàn tất bất đồng bộ: tạo table, tạo bucket policy, deploy function hoặc xóa resource. **Waiter** trong SDK giúp poll trạng thái tới khi resource đạt điều kiện mong muốn hoặc timeout.

Không viết:

~~~java
Thread.sleep(30_000);
assertTableExists();
~~~

Thời gian cố định vừa làm test chậm, vừa không bảo đảm resource đã sẵn sàng. Dùng waiter hoặc polling có timeout/backoff và kiểm tra trạng thái thực.

### 13.3. Eventual consistency trong test

Một số service APIs hoặc workflows có thể cập nhật trạng thái không tức thời. Test nên:

- Chờ điều kiện cụ thể thay vì đợi một khoảng thời gian đoán trước.
- Có deadline rõ và thông báo trạng thái cuối khi timeout.
- Tránh assert ngay rằng một event vừa publish đã xuất hiện ở mọi consumer.
- Phân biệt eventual consistency của service với lỗi do test thiếu permission/network.

Không thêm retry vô hạn để che test flaky; giới hạn attempt và log request IDs/status khi thất bại.

## 14. Kiểm thử AWS SDK async clients

Async client trả về `CompletableFuture`; test cần xác minh cả completion, exception và timeout.

### 14.1. Test successful completion

~~~java
CompletableFuture<PutObjectResponse> future =
    s3Async.putObject(
        PutObjectRequest.builder()
            .bucket("test-images")
            .key("async/sample.txt")
            .build(),
        AsyncRequestBody.fromBytes(
            "async test".getBytes(StandardCharsets.UTF_8))
    );

PutObjectResponse response =
    future.get(5, TimeUnit.SECONDS);

assertNotNull(response.eTag());
~~~

Trong unit test, có thể mock `S3AsyncClient` và trả về `CompletableFuture.completedFuture(...)`. Trong HTTP/LocalStack test, dùng timeout hữu hạn để tránh test treo vô thời hạn.

### 14.2. Test exception path

~~~java
CompletableFuture<PutObjectResponse> failed =
    CompletableFuture.failedFuture(
        S3Exception.builder()
            .statusCode(403)
            .message("AccessDenied")
            .build()
    );

when(s3Async.putObject(
    any(PutObjectRequest.class),
    any(AsyncRequestBody.class)
)).thenReturn(failed);

CompletionException error = assertThrows(
    CompletionException.class,
    () -> service.uploadAsync("private/file.txt", new byte[] {1})
        .join()
);
~~~

`join()` thường bọc lỗi bất đồng bộ trong `CompletionException`; `get()` có thể ném `ExecutionException`. Test cần kiểm tra **root cause** theo API contract, không phụ thuộc một wrapper cụ thể nếu application đã unwrap exception.

### 14.3. Hủy và timeout

- Dùng timeout cho `get` hoặc test framework để ngăn suite bị treo.
- Test cancellation nếu application expose cancel semantics.
- Không coi timeout ở caller đồng nghĩa request chưa tới AWS hoặc operation chưa được thực hiện.
- Với write operations, outcome có thể chưa rõ; cần idempotency key hoặc reconciliation trước khi gửi lại.
- Đóng async client và event-loop resources theo lifecycle.

## 15. Kiểm thử retry, timeout và error handling

### 15.1. Phân loại lỗi trước khi retry

| Lỗi | Hành vi thường phù hợp |
| --- | --- |
| **Throttling / TooManyRequests** | Retry có backoff/jitter trong giới hạn |
| **Transient 5xx / service unavailable** | SDK standard retry strategy có thể retry theo service/error classification |
| **AccessDenied / Invalid credentials** | Không retry liên tục; sửa IAM/credentials |
| **Validation / malformed request** | Không retry cùng request |
| **ResourceNotFound** | Thường không retry trừ khi đang chờ eventual creation có chủ đích |
| **Timeout sau write** | Outcome có thể chưa rõ; kiểm tra idempotency/reconciliation trước retry |

AWS SDK v2 có retry strategy; cấu hình mặc định và khả năng điều chỉnh phụ thuộc SDK version/client. Hãy kiểm tra tài liệu version đang dùng, đặt **max attempts, API call timeout và attempt timeout** theo latency budget. Đừng mặc định retry mọi exception.

### 15.2. Kiểm tra retry bằng HTTP stub

WireMock có thể trả 503 ở một số request đầu rồi 200 ở request tiếp theo. Test xác minh SDK/application có retry trong giới hạn cấu hình và cuối cùng nhận response thành công. Cần lưu ý:

- SDK retry chỉ với lỗi được strategy phân loại là retryable.
- Backoff có jitter; không assert timing chính xác từng mili giây.
- Dùng request count và final result làm assertion chính.
- Giữ số attempt nhỏ để test nhanh và ổn định.
- Không dùng cùng một test để xác nhận toàn bộ AWS service retry behavior.

### 15.3. API call timeout và attempt timeout

Phân biệt:

- **Attempt timeout:** giới hạn cho một HTTP attempt.
- **API call timeout:** giới hạn tổng thời gian của operation, bao gồm retries/backoff.

Nếu tổng deadline của caller là 2 giây nhưng SDK có thể retry 3 lần, phải cấu hình sao cho SDK kết thúc trước deadline hoặc truyền cancellation/timeout xuống đúng cách. Nếu không, request upstream có thể hết hạn trong khi SDK vẫn tiếp tục làm việc.

### 15.4. Không retry side effects một cách mù quáng

Một request `PutObject`/`SendMessage` timeout không luôn chứng minh AWS chưa thực hiện thao tác. Với business operation như charge payment hoặc tạo order:

- Dùng idempotency key hoặc deterministic resource identifier khi API hỗ trợ.
- Kiểm tra trạng thái hiện tại trước khi gửi lại.
- Thiết kế message consumer idempotent.
- Tách lỗi kết nối khỏi kết quả nghiệp vụ đã commit.

## 16. Client lifecycle, thread safety và dependency injection

AWS SDK v2 service clients được thiết kế để **thread-safe và tái sử dụng**. Thông thường, tạo client một lần cho application lifecycle thay vì tạo mới trong từng request.

~~~mermaid
flowchart TD
    APP["Application startup"] --> CFG["Build SDK clients once"]
    CFG --> S3["Shared S3Client"]
    CFG --> DDB["Shared DynamoDbClient"]
    CFG --> SQS["Shared SqsClient"]
    S3 --> REQ["Concurrent application requests"]
    DDB --> REQ
    SQS --> REQ
    REQ --> SHUT["Application shutdown"]
    SHUT --> CLOSE["Close clients / resources"]
~~~

### 16.1. Những điều cần kiểm thử

- Client được tạo với đúng Region, credentials provider, endpoint và timeout.
- Application đóng client/resource khi shutdown.
- Không tạo client mới cho mỗi method invocation.
- Không chia sẻ mutable request builders giữa threads.
- Async client event loop/HTTP connection pool được quản lý đúng.
- Client mock trong test được reset/isolate; không chia sẻ mutable Mockito stubbing giữa test chạy song song.

### 16.2. Dependency injection

Inject service clients qua constructor hoặc factory/provider. Nhờ đó:

- Unit test truyền mock client.
- HTTP contract test truyền client có endpoint override.
- LocalStack test truyền client trỏ container.
- Production wiring tạo client với credentials chain và endpoint mặc định.

Không để business service tự đọc biến môi trường hoặc tự tạo AWS client bên trong method; cách đó khiến test khó kiểm soát endpoint, Region và credentials.

## 17. Tách integration tests trong build và CI/CD

Unit tests nên chạy thường xuyên trên mọi commit. Tests cần Docker hoặc AWS account nên có **test phase/profile riêng**, để developer không vô tình gọi AWS thật khi chạy lệnh test mặc định.

### 17.1. Phân loại tên test

Quy ước đơn giản:

| Loại | Naming convention | Môi trường |
| --- | --- | --- |
| Unit | `*Test.java` | Mock, không cần Docker/AWS |
| HTTP contract | `*ContractTest.java` | WireMock local |
| Emulator integration | `*LocalStackIT.java` | Docker/Testcontainers |
| AWS integration | `*AwsIT.java` | Sandbox account/role |

Có thể dùng JUnit tags như `unit`, `localstack` và `aws-integration` để chọn suite. Không để AWS integration tests tự chạy trong profile mặc định của mọi developer.

### 17.2. Maven Failsafe profile (minh họa)

~~~xml
<profiles>
  <profile>
    <id>aws-integration</id>
    <build>
      <plugins>
        <plugin>
          <groupId>org.apache.maven.plugins</groupId>
          <artifactId>maven-failsafe-plugin</artifactId>
          <executions>
            <execution>
              <goals>
                <goal>integration-test</goal>
                <goal>verify</goal>
              </goals>
              <configuration>
                <includes>
                  <include>**/*AwsIT.java</include>
                </includes>
              </configuration>
            </execution>
          </executions>
        </plugin>
      </plugins>
    </build>
  </profile>
</profiles>
~~~

Ví dụ chỉ minh họa cách tách profile; version plugin và test selection phải theo parent build hiện có. Unit tests vẫn chạy riêng; `mvn -Paws-integration verify` chỉ nên chạy ở pipeline/job có account guard và credentials đúng.

### 17.3. Pipeline stages

~~~mermaid
flowchart TD
    PR["Pull request"] --> UNIT["Unit tests / Mockito"]
    UNIT --> HTTP["WireMock contract tests"]
    HTTP --> LOCAL["LocalStack tests (Docker)"]
    LOCAL --> BUILD["Package / static checks"]
    BUILD --> APPROVAL["Protected integration stage"]
    APPROVAL --> ROLE["Assume sandbox role"]
    ROLE --> GUARD["STS account + Region guard"]
    GUARD --> AWSIT["Small AWS integration suite"]
    AWSIT --> CLEAN["Cleanup + report resources"]
~~~

Một pipeline an toàn:

1. Unit và HTTP contract tests chạy không có AWS credentials.
2. LocalStack suite chạy trên runner có Docker.
3. AWS integration job chạy trong stage được bảo vệ, dùng OIDC/assume-role.
4. STS guard xác nhận account ID và Region allowlist trước khi tạo tài nguyên.
5. Test tạo resources theo run ID, cleanup trong finally và lưu report.
6. Job janitor có thể tìm tài nguyên mồ côi theo tag/expiry trong sandbox.

### 17.4. Không để profile local trỏ nhầm AWS

Đối với test endpoint:

- Dùng fake credentials và endpoint local được truyền rõ ràng.
- Có assertion rằng URI host thuộc `localhost`, loopback hoặc hostname container mong đợi.
- Không fallback sang default AWS endpoint khi endpoint test thiếu.
- Tách configuration class/profile và fail fast nếu test property không tồn tại.

Đối với AWS sandbox:

- Không dùng endpoint override local.
- Không dùng credentials fake.
- Bắt buộc account guard và allowlisted Region.
- Không dùng profile `default` mơ hồ trên CI runner.

## 18. Troubleshooting các lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| **Unable to load credentials** | Không có profile/role/credential provider hợp lệ | Kiểm tra SSO login, profile, CI identity và credential chain |
| **The security token included in the request is invalid** | Session hết hạn hoặc credentials không hợp lệ | Refresh SSO/assume-role; không chuyển sang access key hardcode |
| **SignatureDoesNotMatch** | Region, service signing scope, clock hoặc endpoint/path không đúng | Kiểm tra Region, system clock, path-style và canonical request |
| **AccessDenied** | IAM identity/resource policy/KMS policy thiếu quyền | Xem CloudTrail và policy; không retry vô hạn |
| **Connection refused** | LocalStack/WireMock chưa start hoặc sai port | Chờ container readiness, dùng endpoint dynamic chính xác |
| **UnknownHost / timeout** | DNS, VPC route, Security Group, proxy hoặc endpoint sai | Kiểm tra network path và endpoint host |
| **S3 bucket addressing mismatch** | Path-style/virtual-host-style khác với emulator | Cấu hình S3 service-specific addressing trong test client |
| **DynamoDB target mismatch** | WireMock stub sai `X-Amz-Target` | Xác minh operation name và request protocol |
| **NoSuchBucket / ResourceNotFound** | Fixture chưa tạo, sai Region hoặc cleanup chạy quá sớm | Tạo resource trước test, dùng waiter và namespace riêng |
| **Throttling trong sandbox** | Test chạy song song quá mức hoặc quota thấp | Giới hạn concurrency, backoff và test scope |
| **Test pass local nhưng fail AWS** | Emulator không mô phỏng IAM/network/service semantics đầy đủ | Tạo sandbox integration test và so CloudTrail/request IDs |
| **Test flaky do sleep** | Eventual consistency hoặc provisioning chưa hoàn tất | Dùng waiter/polling có deadline và trạng thái cuối |
| **Resource còn sót sau test** | Process bị kill trước cleanup hoặc delete bất đồng bộ | Tag run ID, janitor và waiter xác nhận xóa |
| **Client threads không dừng** | Client/HTTP transport chưa close | Quản lý client lifecycle bằng try-with-resources/DI shutdown |

### 18.1. Kiểm tra SigV4 theo thứ tự

Khi request bị AWS từ chối vì signature:

1. Xác nhận client đang dùng Region chính xác.
2. Kiểm tra credentials provider trả session còn hạn.
3. Đồng bộ system clock của runner.
4. Kiểm tra endpoint, host header, path-style và proxy rewrite.
5. Đọc error code/request ID trong response và CloudTrail nếu có.
6. Tránh log `Authorization` header hoặc session token trong CI output.

## 19. Case study: kiểm thử luồng S3 → DynamoDB → SQS

### 19.1. Bối cảnh

Một API upload ảnh sản phẩm:

~~~text
1. Upload image bytes to S3
2. Save product image metadata in DynamoDB
3. Publish ProductImageUploaded event to SQS
4. Return image key and event/message reference
~~~

Các bước có thể thành công một phần. Ví dụ S3 upload xong nhưng DynamoDB write lỗi; hoặc DynamoDB commit xong nhưng SQS publish timeout. Test phải xác định behavior và recovery contract.

### 19.2. Ma trận test theo tầng

| Test | Công cụ | Assertion chính |
| --- | --- | --- |
| Service validate file type/size | JUnit | Reject invalid input trước khi gọi SDK |
| S3 upload gọi đúng bucket/key/content type | Mockito | Request model đúng |
| DynamoDB conditional write | Mockito | Condition expression và conflict mapping |
| SQS event body/attributes | Mockito | Payload, queue URL, message group/deduplication |
| S3 path, headers, SigV4 creation | WireMock | HTTP contract và response parsing |
| S3 put/get local | LocalStack | SDK và emulator phối hợp được |
| IAM role và bucket policy | AWS sandbox | Thao tác được phép/được từ chối đúng |
| Cleanup và resource lifecycle | AWS sandbox | Bucket/table/queue được xóa theo policy |

### 19.3. Xử lý partial failure

~~~mermaid
flowchart TD
    START["Upload request"] --> S3["Put object to S3"]
    S3 --> DDB["Write metadata to DynamoDB"]
    DDB --> SQS["Publish event to SQS"]
    SQS --> OK["Return success"]
    S3 -->|"Failure"| FAIL["Return upload error"]
    DDB -->|"Failure"| COMP["Delete object or mark orphan for cleanup"]
    SQS -->|"Timeout / unknown result"| RECON["Idempotency key + reconcile publish"]
    COMP --> FAIL
    RECON --> DECIDE["Determine message state before retry"]
~~~

Không giả định ba dịch vụ chia sẻ một transaction ACID. Có thể dùng outbox trong DynamoDB/RDS hoặc trạng thái workflow bền vững để xử lý event publish đáng tin cậy; test nên mô phỏng từng điểm fail và xác minh không tạo duplicate side effects.

### 19.4. Tách test theo rủi ro

- Unit tests xác nhận validation và mapping logic.
- Mock tests xác nhận đúng request models và xử lý service exceptions.
- WireMock xác nhận SDK request signing/serialization và parse response.
- LocalStack xác nhận luồng API cơ bản với emulator.
- AWS sandbox xác nhận IAM, KMS, bucket policies, SQS policies, VPC và quotas.

Một test end-to-end sandbox nhỏ là đủ để chứng minh wiring thật; không cần tạo hàng nghìn tài nguyên thật mỗi lần chạy pull request.

## 20. Bài thực hành: xây dựng test suite nhiều tầng

### 20.1. Hoàn thiện helper S3 client cho WireMock

Đoạn test ở mục 5 có thể dùng helper sau để bảo đảm mọi test đều trỏ tới local endpoint và dùng fake credentials:

~~~java
private S3Client buildS3Client(String endpoint) {
    AwsCredentialsProvider fakeCredentials =
        StaticCredentialsProvider.create(
            AwsBasicCredentials.create(
                "test-access-key",
                "test-secret-key"
            )
        );

    return S3Client.builder()
        .endpointOverride(URI.create(endpoint))
        .region(Region.US_EAST_1)
        .credentialsProvider(fakeCredentials)
        .serviceConfiguration(
            S3Configuration.builder()
                .pathStyleAccessEnabled(true)
                .build()
        )
        .build();
}
~~~

Helper này chỉ nên nằm trong test source set. Không chia sẻ nó với production configuration hoặc cho phép endpoint được truyền từ request người dùng.

### 20.2. Các bước thực hành

1. Viết `ProductImageService` nhận `S3Client` qua constructor.
2. Dùng Mockito kiểm tra bucket, key, content type và AccessDenied handling.
3. Dựng WireMock trên dynamic port; build S3 client bằng helper trên.
4. Stub `PUT /bucket/key`, trả ETag và xác minh Authorization header có SigV4 scheme.
5. Trả HTTP 500 ở lần đầu rồi thành công ở lần tiếp theo; xác minh retry count theo retry strategy được cấu hình.
6. Chạy cùng luồng put/get trên LocalStack/Testcontainers.
7. Tạo AWS sandbox role riêng, kiểm tra account bằng STS trước khi tạo resource thật.
8. Tạo bucket có run ID, upload object, đọc lại và xóa bucket trong cleanup.
9. Kiểm tra CloudTrail/IAM policy khi sandbox test bị AccessDenied.
10. Chạy test suite song song để tìm race condition và resource name collision.

### 20.3. Kết quả cần lưu

- Unit/contract/emulator/AWS integration test reports tách biệt.
- SDK version, Region, account ID đã mask theo chính sách và run ID.
- Request ID/error code khi AWS thật trả lỗi.
- Danh sách resource test đã tạo và trạng thái cleanup.
- Thời lượng test, retry count và chi phí phát sinh nếu có.

Không lưu access key, secret key, session token, Authorization header hoặc payload chứa dữ liệu nhạy cảm trong test artifacts.

## 21. Bài tập củng cố

### Bài 1 — Chọn test level

Bạn cần kiểm tra `ProductService` gọi repository đúng khi sản phẩm không tồn tại. Nên dùng mock hay AWS sandbox?

**Gợi ý:** unit test/mock; không cần tạo AWS resource.

### Bài 2 — Endpoint override

Một test dùng `endpointOverride` tới WireMock nhưng nhận lỗi thiếu credentials. Vì sao SDK vẫn cần credentials khi server không phải AWS?

**Gợi ý:** SDK thường ký request bằng SigV4; dùng fake credentials và Region để tạo signing scope.

### Bài 3 — Region mismatch

Request gửi đến endpoint local nhưng chữ ký không hợp lệ vì signing Region khác Region mà stub/emulator mong đợi. Cần kiểm tra gì?

**Gợi ý:** Region trên client, signing scope, endpoint-specific configuration và canonical request.

### Bài 4 — Mock hay WireMock?

Bạn cần xác minh S3 client tạo path `/bucket/key`, header content type và SigV4 Authorization header. Chọn công cụ nào?

**Gợi ý:** HTTP stub/WireMock với SDK client thật và endpoint override; Mockito không đi qua HTTP pipeline.

### Bài 5 — LocalStack pass, AWS fail

Test create bucket pass trên LocalStack nhưng sandbox account trả AccessDenied. Điều đó có mâu thuẫn không?

**Gợi ý:** không. Emulator không chứng minh IAM/resource policy của AWS thật. Kiểm tra caller identity, policy, SCP, KMS và bucket policy.

### Bài 6 — Sandbox guard

Một pipeline dùng profile mặc định và account ID không được mong đợi. Test có thể tạo resource trước khi phát hiện lỗi không?

**Gợi ý:** STS account guard phải chạy trước mọi thao tác tạo/sửa tài nguyên; IAM/SCP cần giới hạn thêm.

### Bài 7 — Retry sau timeout

SQS `SendMessage` timeout. Ứng dụng retry và nhận hai message. Thiết kế nào giúp tránh duplicate business processing?

**Gợi ý:** idempotency key/deduplication strategy, consumer idempotency và reconcile outcome; FIFO deduplication chỉ giúp trong phạm vi semantics/thời hạn dịch vụ.

### Bài 8 — Cleanup S3

Test tạo bucket versioned, xóa object key rồi xóa bucket nhưng nhận BucketNotEmpty. Vì sao?

**Gợi ý:** phải xóa object versions/delete markers và multipart uploads trước khi xóa bucket.

### Bài 9 — Async test treo

Test gọi `join()` mà future không hoàn tất; suite chạy vô thời hạn. Cách sửa?

**Gợi ý:** dùng timeout hữu hạn, kiểm tra service/container readiness và cleanup client/event loop.

### Bài 10 — Pagination

`ListObjectsV2` trả trang đầu có `IsTruncated=true`. Code chỉ dùng `response.contents()` một lần. Lỗi gì?

**Gợi ý:** bỏ sót các trang tiếp theo; dùng paginator hoặc continuation token.

### Bài 11 — Thread safety

Một ứng dụng tạo `S3Client` mới cho mỗi request. Tác động và cách cải thiện?

**Gợi ý:** tăng overhead connection/thread/resource; tái sử dụng client thread-safe qua dependency injection và đóng khi shutdown.

### Bài 12 — Test account isolation

Một AWS integration test chạy song song trên nhiều CI jobs và dùng cùng tên DynamoDB table. Điều gì có thể xảy ra?

**Gợi ý:** collision, test interference và cleanup nhầm tài nguyên; thêm run ID vào resource names/tags và giới hạn quyền theo prefix.

## 22. Checklist triển khai test production-ready

- [ ] AWS SDK BOM quản lý version đồng bộ; project dùng rõ SDK v2 và không trộn SDK v1 imports.
- [ ] Unit tests mock service clients và tập trung vào business behavior.
- [ ] HTTP contract tests dùng WireMock/local endpoint, Region và fake credentials.
- [ ] Endpoint tùy chỉnh chỉ bật trong test configuration; không thể fallback nhầm sang AWS thật.
- [ ] SigV4 test kiểm tra scheme/scope phù hợp, không log toàn bộ Authorization header.
- [ ] LocalStack image và Testcontainers version được pin; container readiness/lifecycle được quản lý.
- [ ] Hiểu emulator limitations; có AWS sandbox test cho IAM, network, quotas và service semantics cần xác nhận.
- [ ] Sandbox account ID và allowed Region được kiểm tra qua STS trước khi tạo resource.
- [ ] CI dùng OIDC/assume-role hoặc session ngắn hạn; không lưu long-lived keys trong source/pipeline logs.
- [ ] IAM role test có least privilege, không thể assume production role.
- [ ] Tài nguyên có run ID, owner/expiry tags, cleanup trong finally và janitor cho resource mồ côi.
- [ ] S3 versioning/multipart uploads, DynamoDB waiters và SQS queue lifecycle được cleanup đúng.
- [ ] Retry, timeout, throttling, AccessDenied và unknown write outcome có test.
- [ ] Pagination, async completion/failure, client shutdown và parallel execution được kiểm thử.
- [ ] Unit, contract, LocalStack và AWS integration suites được tách riêng trong build/CI.
- [ ] Reports không chứa credentials, tokens, PII hoặc payload nhạy cảm.
- [ ] Có budget alerts, concurrency limits và resource quotas cho sandbox.

## 23. Ghi nhớ

**Kiểm thử AWS SDK for Java cần nhiều mức bảo vệ khác nhau:**

1. **Mockito** kiểm tra business logic và cách service dùng SDK client mà không gọi network.
2. **WireMock + endpoint override** kiểm tra HTTP request/response, serialization và SigV4 request generation; vẫn cần Region và fake credentials.
3. **LocalStack/Testcontainers** giúp kiểm thử tích hợp với emulator có thể tái tạo, nhưng không chứng minh IAM, networking hoặc mọi service semantics của AWS thật.
4. **AWS sandbox account** kiểm chứng IAM, KMS, quotas, VPC, service behavior và lifecycle thật; phải có account guard, least privilege, budget và cleanup.
5. AWS SDK v2 clients nên được tái sử dụng, inject qua constructor/factory và đóng theo application lifecycle.
6. Retry/timeout phải có giới hạn; với write operations, timeout có thể tạo outcome không rõ nên cần idempotency và reconciliation.
7. Tài nguyên test phải có namespace riêng, run ID và cleanup; test report không được làm lộ credentials hoặc dữ liệu nhạy cảm.

Một test suite tốt cho thấy **logic đúng, request đúng, integration đủ tin cậy và sandbox an toàn**. Không một mock hay emulator nào tự chứng minh tất cả bốn điều đó.

### Tài liệu chính thức và tham khảo

- [AWS SDK for Java 2.x Developer Guide](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/home.html) — hướng dẫn tổng thể SDK v2.
- [Service clients](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/service-clients.html) — tạo và tái sử dụng service clients.
- [Credentials provider chain](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/credentials-chain.html) — nguồn credentials và provider chain.
- [Configure service endpoints](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/endpoint-config.html) — endpoint configuration và endpoint override.
- [Retry strategy](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/retry-strategy.html) — retry behavior trong SDK v2.
- [AWS SDK for Java API reference](https://sdk.amazonaws.com/java/api/latest/) — request/response builders và service clients.
- [AWS STS GetCallerIdentity](https://docs.aws.amazon.com/STS/latest/APIReference/API_GetCallerIdentity.html) — xác định account/caller.
- [Testcontainers LocalStack module](https://java.testcontainers.org/modules/localstack/) — chạy LocalStack bằng Testcontainers.
- [LocalStack documentation](https://docs.localstack.cloud/) — service coverage và cấu hình emulator.
- [WireMock documentation](https://wiremock.org/docs/) — HTTP stubbing và request verification.
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/) — test lifecycle, tags và extensions.
- [Mockito documentation](https://javadoc.io/doc/org.mockito/mockito-core/latest/org/mockito/Mockito.html) — mocks, stubbing và verification.
