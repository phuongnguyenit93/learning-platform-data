# Bảo vệ API ứng dụng bằng Cognito và kiểm tra JWT

Một API không thể chỉ dựa vào việc client gửi lên một chuỗi JWT có vẻ hợp lệ. Backend phải xác minh token do đúng identity provider phát hành, token còn hạn, được cấp cho đúng ứng dụng và có quyền thực hiện hành động đang gọi. Nếu chỉ kiểm tra chữ ký mà không kiểm tra scope, một token hợp lệ nhưng chỉ có quyền đọc hồ sơ người dùng vẫn có thể bị dùng nhầm để gọi API quản lý đơn hàng.

Trong bài thực hành này, bạn xây dựng một luồng xác thực người dùng bằng Amazon Cognito User Pool, cấp quyền API bằng OAuth 2.0 custom scope và bảo vệ endpoint bằng Amazon API Gateway HTTP API JWT Authorizer. Một AWS Lambda function làm backend để hiển thị những claims đã được API Gateway xác minh. Luồng đăng nhập dùng Authorization Code Grant với PKCE, phù hợp public client chạy trong browser hoặc ứng dụng di động.

Bài thuộc module CLOUD_PROVIDERS_AWS. Bạn sẽ thực hành tạo user pool, app client, resource server, managed login domain, JWT authorizer và route scope; sau đó kiểm thử request không token, token sai, ID token, access token thiếu scope và access token có đúng scope.

## 1. Kết quả cần đạt

Sau lab, bạn có thể:

- Phân biệt authentication, authorization, Cognito User Pool và Identity Pool.
- Tạo User Pool, public app client và managed login domain.
- Định nghĩa resource server cùng custom scopes.
- Dùng Authorization Code Grant và PKCE để nhận ID, access và refresh token.
- Cấu hình API Gateway HTTP API JWT Authorizer với issuer và audience.
- Gắn authorization scope vào từng route.
- Xác minh API từ chối request không có token hoặc không đủ quyền.
- Đọc claims đã được xác minh trong Lambda integration.
- Hiểu giới hạn của JWT revocation khi API Gateway xác thực token theo kiểu offline.

## 2. Kiến trúc lab

~~~mermaid
flowchart LR
    U[Browser / local PKCE client] -->|1. Authorization Code + PKCE| C[Cognito Managed Login]
    C -->|2. ID / Access / Refresh tokens| U
    U -->|3. Bearer access token| A[API Gateway HTTP API]
    A -->|4. JWT validation + scope check| J[JWT Authorizer]
    J -->|5. Verified claims| L[Lambda integration]
    L -->|6. JSON response| U
    C --- P[User Pool / App Client / Resource Server]
    J --- K[Issuer JWKS public keys]
~~~

Vai trò từng thành phần:

| Thành phần | Vai trò |
|---|---|
| Cognito User Pool | Quản lý user, đăng nhập, xác minh danh tính và phát hành JWT |
| App client | Đại diện cho một ứng dụng; cấu hình OAuth flow, callback URL và scope |
| Resource server | Định nghĩa các custom scope bảo vệ API |
| Managed login domain | Cung cấp trang đăng nhập và OAuth endpoints |
| PKCE client | Tạo code verifier/challenge, nhận authorization code và đổi token |
| API Gateway HTTP API | Tiếp nhận request và thực thi JWT Authorizer |
| JWT Authorizer | Kiểm tra chữ ký, issuer, audience/client ID, thời hạn và scope |
| Lambda | Xử lý nghiệp vụ sau khi request đã được authorizer chấp nhận |

Lab dùng HTTP API JWT Authorizer. API Gateway REST API cũng hỗ trợ Cognito User Pool Authorizer nhưng cấu hình và cách chọn token có khác biệt; không áp dụng nguyên xi các bước HTTP API cho REST API.

## 3. Phân biệt Authentication và Authorization

Authentication trả lời câu hỏi "người dùng là ai?". Cognito User Pool xác minh thông tin đăng nhập hoặc identity provider rồi phát hành token.

Authorization trả lời câu hỏi "người dùng được phép làm gì?". API Gateway kiểm tra token và scope trước khi chuyển request tới backend.

Ví dụ:

- Người dùng đăng nhập thành công: authentication đã hoàn tất.
- Người dùng có scope orders/read: có thể gọi GET /orders.
- Người dùng không có scope orders/write: không được gọi POST /orders.

Đăng nhập thành công không đồng nghĩa người dùng được quyền gọi mọi API.

## 4. User Pool và Identity Pool khác nhau thế nào?

| Dịch vụ | Mục đích | Kết quả thường nhận |
|---|---|---|
| Cognito User Pool | Directory và xác thực người dùng; hỗ trợ OAuth/OIDC và federation | ID token, access token, refresh token |
| Cognito Identity Pool | Liên kết identity với AWS credentials tạm thời | AWS credentials qua STS để truy cập dịch vụ AWS |

Lab này dùng User Pool vì API cần xác minh danh tính và quyền qua JWT. Identity Pool không cần thiết nếu Lambda/backend là thành phần duy nhất truy cập AWS resources thay mặt người dùng.

## 5. ID token, access token và refresh token

Cognito có ba loại token chính:

| Token | Mục đích | Dữ liệu/khả năng |
|---|---|---|
| ID token | Chứng minh user đã đăng nhập và cung cấp identity claims | sub, email và claims hồ sơ được phép đọc |
| Access token | Chứng minh quyền truy cập resource/API | scope, client_id, token_use=access và claims liên quan |
| Refresh token | Xin access token và ID token mới khi token hiện tại hết hạn | Không gửi tới API resource server |

Đối với API, dùng access token. ID token dành cho client hiểu danh tính user; không dùng ID token thay access token khi route cần authorization scope.

API Gateway JWT Authorizer không tự suy luận token là access token hay ID token chỉ từ định dạng JWT. AWS khuyến nghị cấu hình authorization scopes trên route để buộc token có scope mà API yêu cầu. Đây là lý do lab tạo custom scope và gắn scope vào route.

## 6. Điều kiện và tài nguyên

Bạn cần:

- AWS account có quyền tạo Cognito User Pool, API Gateway HTTP API, Lambda và IAM role.
- AWS CLI v2 nếu muốn dùng các lệnh kiểm tra tùy chọn.
- Node.js 18 trở lên để chạy local PKCE callback script.
- PowerShell 5.1 trở lên hoặc shell có thể gửi HTTP form request.
- Một trình duyệt để đăng nhập Cognito Managed Login.

Chọn một Region duy nhất cho User Pool, API Gateway và Lambda, ví dụ ap-southeast-1. Ghi lại Region đã chọn vì Region trong issuer URL phải trùng Region của User Pool.

Sử dụng tài khoản thử nghiệm và dữ liệu giả. Không đưa password, client secret, authorization code, access token hoặc refresh token production vào source control, ticket hay log công khai.

## 7. Tạo Cognito User Pool

1. Mở Amazon Cognito console.
2. Chọn User Pools rồi tạo user pool mới.
3. Chọn phương thức đăng nhập bằng email hoặc username/email theo nhu cầu lab.
4. Bật xác minh email nếu muốn dùng email làm định danh đăng nhập.
5. Chọn cấu hình password policy phù hợp.
6. Tạo User Pool và ghi lại User Pool ID.

User Pool ID có dạng:

~~~text
ap-southeast-1_AbCdEf123
~~~

Không dùng User Pool ID làm app client ID. Đây là hai định danh khác nhau và được sử dụng ở hai vị trí khác nhau trong issuer/audience.

## 8. Tạo resource server và custom scopes

Resource server đại diện cho API mà access token sẽ bảo vệ. Trong User Pool:

1. Mở Domain hoặc Resource servers trong phần cấu hình User Pool.
2. Chọn Create resource server.
3. Đặt tên hiển thị: Orders API.
4. Đặt identifier: https://api.example.com
5. Tạo custom scope orders.read với mô tả "Đọc danh sách đơn hàng".
6. Tạo custom scope orders.write với mô tả "Tạo hoặc cập nhật đơn hàng".

Scope đầy đủ có dạng:

~~~text
https://api.example.com/orders.read
https://api.example.com/orders.write
~~~

Amazon Cognito ghép resource server identifier với scope name bằng dấu gạch chéo. Identifier có thể là một tên ngắn hoặc URL; dùng URL giúp scope dễ nhận biết là dành cho API nào, nhưng làm token dài hơn.

Scope là quyền mà ứng dụng yêu cầu và API kiểm tra. Đặt tên scope theo hành động hoặc tài nguyên, tránh tên chung chung như admin nếu API có thể chia nhỏ quyền đọc/ghi.

## 9. Tạo public app client cho ứng dụng web

Tạo một app client riêng cho ứng dụng thử nghiệm:

1. Mở App clients trong User Pool.
2. Tạo app client loại Single-page application hoặc public client.
3. Không tạo client secret vì browser/mobile app không có nơi đáng tin cậy để giữ secret tĩnh.
4. Bật OAuth 2.0 authorization code grant.
5. Không bật implicit grant cho lab này.
6. Thêm callback URL: http://localhost:3000/callback
7. Thêm sign-out URL: http://localhost:3000/
8. Chọn identity provider Cognito User Pool.
9. Cho phép OIDC scopes openid, email và profile.
10. Cho phép custom scopes https://api.example.com/orders.read và https://api.example.com/orders.write.
11. Lưu cấu hình và ghi lại App client ID.

Cognito chỉ cho phép HTTP callback URL với localhost cho mục đích kiểm thử. Khi triển khai thực tế, dùng HTTPS và callback URL đã đăng ký chính xác.

App client ID có dạng chuỗi ký tự dài. Đây là giá trị sẽ được dùng làm audience của JWT authorizer trong lab này.

## 10. Cấu hình Managed Login domain

OAuth authorization code flow cần User Pool domain.

1. Mở Domain trong User Pool.
2. Chọn Cognito domain hoặc custom domain theo yêu cầu.
3. Với lab, chọn Cognito domain và nhập prefix duy nhất trong Region.
4. Chọn cấu hình Managed login.
5. Lưu domain.

Domain có dạng:

~~~text
https://<domain-prefix>.auth.<region>.amazoncognito.com
~~~

Ví dụ domain-prefix là lab-orders-abc123 và Region là ap-southeast-1:

~~~text
https://lab-orders-abc123.auth.ap-southeast-1.amazoncognito.com
~~~

Ghi lại domain prefix/host. Các endpoint OAuth được dùng trong lab:

~~~text
/oauth2/authorize
/oauth2/token
/oauth2/revoke
~~~

## 11. Tạo người dùng thử nghiệm

Bạn có thể tạo user qua Cognito console hoặc cho phép self sign-up trên Managed Login.

Với cách tạo thủ công:

1. Mở Users trong User Pool.
2. Chọn Create user.
3. Nhập email dành riêng cho lab.
4. Xác minh email theo cấu hình.
5. Đặt password thử nghiệm hoặc hoàn tất bước đổi temporary password.
6. Kiểm tra user ở trạng thái có thể đăng nhập.

Nếu User Pool yêu cầu xác minh email, hãy hoàn tất xác minh trước khi thực hiện authorization flow. Không dùng email thật của người khác.

## 12. Tạo Lambda backend

Trong Lambda console:

1. Tạo function tên orders-api-lab.
2. Chọn runtime Python 3.12 hoặc runtime Python được Region hỗ trợ.
3. Tạo execution role với AWSLambdaBasicExecutionRole để ghi CloudWatch Logs.
4. Dán handler sau vào index.py hoặc file handler mà runtime yêu cầu.
5. Deploy function.

~~~python
import json


def handler(event, context):
    request_context = event.get("requestContext", {})
    authorizer = request_context.get("authorizer", {})
    jwt = authorizer.get("jwt", {})
    claims = jwt.get("claims", {})
    scopes = jwt.get("scopes", [])

    body = {
        "message": "Request được Cognito JWT Authorizer chấp nhận",
        "method": request_context.get("http", {}).get("method"),
        "path": event.get("rawPath"),
        "subject": claims.get("sub"),
        "username": claims.get("username"),
        "token_use": claims.get("token_use"),
        "scopes": scopes
    }

    return {
        "statusCode": 200,
        "headers": {
            "content-type": "application/json",
            "cache-control": "no-store"
        },
        "body": json.dumps(body)
    }
~~~

Handler chỉ hiển thị một số claims phục vụ học tập. Không trả access token, refresh token, toàn bộ claims nhạy cảm hoặc thông tin nội bộ của người dùng ra response production.

API Gateway sẽ chuyển các JWT claims đã xác minh tới Lambda trong:

~~~text
event.requestContext.authorizer.jwt.claims
~~~

Danh sách scopes có thể đọc từ:

~~~text
event.requestContext.authorizer.jwt.scopes
~~~

Lambda không cần tự parse và xác minh chữ ký token trong bài lab này vì API Gateway thực hiện bước đó trước khi gọi integration.

## 13. Tạo API Gateway HTTP API

1. Mở API Gateway console.
2. Chọn Create API.
3. Chọn HTTP API.
4. Tạo Lambda integration trỏ tới orders-api-lab.
   - Nếu console hỏi Payload format version, chọn 2.0 vì handler đọc requestContext.http.method, rawPath và requestContext.authorizer.jwt.
5. Đặt tên API, ví dụ orders-http-api.
6. Tạo route GET /orders.
7. Gắn Lambda integration vào route.
8. Tạo stage, ví dụ $default, và bật auto-deploy.
9. Ghi lại Invoke URL.

Invoke URL thường có dạng:

~~~text
https://<api-id>.execute-api.<region>.amazonaws.com
~~~

Route hoàn chỉnh:

~~~text
GET https://<api-id>.execute-api.<region>.amazonaws.com/orders
~~~

Nếu dùng custom domain hoặc stage có tên riêng, hãy dùng đúng Invoke URL tương ứng. HTTP API với stage $default thường không cần thêm stage segment trong URL.

## 14. Tạo JWT Authorizer cho HTTP API

Trong API Gateway:

1. Mở API vừa tạo.
2. Chọn Authorization.
3. Chọn Manage authorizers rồi Create.
4. Chọn Authorizer type là JWT.
5. Đặt tên CognitoUserPoolJwt.
6. Identity source: $request.header.Authorization.
7. Issuer URL:

~~~text
https://cognito-idp.<region>.amazonaws.com/<user-pool-id>
~~~

8. Audience: App client ID của public app client.
9. Tạo authorizer.

Issuer phải trùng chính xác issuer trong JWT. Ví dụ:

~~~text
https://cognito-idp.ap-southeast-1.amazonaws.com/ap-southeast-1_AbCdEf123
~~~

Audience trong lab là App client ID. Với Cognito access token thông thường, claim client_id được dùng khi token không có aud. API Gateway kiểm tra aud nếu claim này hiện diện; chỉ khi không có aud mới kiểm tra client_id. Nếu bạn bật resource binding khiến access token có aud, phải cấu hình audience theo resource URI tương ứng.

## 15. Gắn authorizer và scope vào route

1. Mở Routes.
2. Chọn GET /orders.
3. Chọn Authorization type là JWT.
4. Chọn authorizer CognitoUserPoolJwt.
5. Thêm authorization scope:

~~~text
https://api.example.com/orders.read
~~~

6. Lưu thay đổi và deploy nếu stage không bật auto-deploy.

Nếu sau này tạo POST /orders, hãy gắn scope:

~~~text
https://api.example.com/orders.write
~~~

Khi route có authorization scopes, API Gateway yêu cầu token chứa ít nhất một scope trong danh sách route. Nếu route cần nhiều quyền đồng thời theo logic AND, không chỉ đưa nhiều scope vào danh sách rồi giả định API Gateway sẽ yêu cầu tất cả; hãy thực hiện kiểm tra bổ sung ở backend hoặc thiết kế policy phù hợp.

## 16. Tạo PKCE verifier và callback server cục bộ

Để lấy custom scope, dùng OAuth authorization endpoint của Cognito. Không dùng InitiateAuth cho bước này: API InitiateAuth/AdminInitiateAuth chỉ cấp scope aws.cognito.signin.user.admin, không cấp custom resource-server scopes.

Tạo file pkce-login.mjs trên máy phát triển:

~~~javascript
import { createServer } from "node:http";
import { randomBytes, createHash } from "node:crypto";

const domain = process.env.COGNITO_DOMAIN;
const clientId = process.env.COGNITO_CLIENT_ID;
const redirectUri = "http://localhost:3000/callback";
const defaultScopes =
  "openid email profile https://api.example.com/orders.read";
const scopes = process.env.OAUTH_SCOPES || defaultScopes;

if (!domain || !clientId) {
  throw new Error("Set COGNITO_DOMAIN and COGNITO_CLIENT_ID first.");
}

const base64url = (value) => value.toString("base64url");
const verifier = base64url(randomBytes(32));
const challenge = base64url(
  createHash("sha256").update(verifier).digest()
);
const state = base64url(randomBytes(24));

const params = new URLSearchParams({
  response_type: "code",
  client_id: clientId,
  redirect_uri: redirectUri,
  scope: scopes,
  code_challenge: challenge,
  code_challenge_method: "S256",
  state
});

const authorizeUrl =
  "https://" + domain + "/oauth2/authorize?" + params.toString();

const server = createServer((request, response) => {
  const callbackUrl = new URL(request.url, redirectUri);

  if (callbackUrl.pathname !== "/callback") {
    response.writeHead(404);
    response.end("Not found");
    return;
  }

  const returnedState = callbackUrl.searchParams.get("state");
  const code = callbackUrl.searchParams.get("code");
  const oauthError = callbackUrl.searchParams.get("error");

  if (returnedState !== state) {
    response.writeHead(400);
    response.end("State mismatch. Reject this response.");
    server.close();
    return;
  }

  if (oauthError || !code) {
    response.writeHead(400);
    response.end("Authorization failed: " + (oauthError || "missing code"));
    console.error("OAuth error:", oauthError);
    server.close();
    return;
  }

  response.writeHead(200, { "content-type": "text/plain; charset=utf-8" });
  response.end("Sign-in completed. Return to the terminal.");

  console.log("AUTH_CODE=" + code);
  console.log("CODE_VERIFIER=" + verifier);
  console.log("STATE_VALID=true");
  server.close();
});

server.listen(3000, () => {
  console.log("Open this URL in your browser:\n");
  console.log(authorizeUrl);
  console.log("\nWaiting for Cognito callback on localhost:3000...");
});
~~~

Đoạn script tạo code verifier ngẫu nhiên, tính SHA-256 code challenge, tạo state chống CSRF và nhận callback tại loopback localhost. Code verifier chỉ được dùng khi đổi authorization code.

## 17. Chạy PKCE login

Mở PowerShell tại thư mục chứa pkce-login.mjs và đặt biến môi trường:

~~~powershell
$env:COGNITO_DOMAIN = "<domain-prefix>.auth.<region>.amazoncognito.com"
$env:COGNITO_CLIENT_ID = "<app-client-id>"
$env:OAUTH_SCOPES = "openid email profile https://api.example.com/orders.read"
node .\pkce-login.mjs
~~~

Script in authorization URL. Mở URL trong browser, đăng nhập bằng user thử nghiệm và chấp thuận nếu Managed Login yêu cầu. Sau khi đăng nhập, Cognito redirect về localhost:3000/callback. Terminal hiển thị AUTH_CODE và CODE_VERIFIER.

Không chia sẻ authorization code hoặc verifier. Authorization code chỉ dùng một lần và verifier cần được giữ bí mật tới khi hoàn tất token exchange.

## 18. Đổi authorization code lấy token

Trong cùng PowerShell session, nhập code và verifier vừa nhận:

~~~powershell
$authorizationCode = Read-Host "Paste AUTH_CODE"
$codeVerifier = Read-Host "Paste CODE_VERIFIER"
$redirectUri = "http://localhost:3000/callback"
$tokenEndpoint = "https://$env:COGNITO_DOMAIN/oauth2/token"

$tokenRequest = @{
  Method = "Post"
  Uri = $tokenEndpoint
  ContentType = "application/x-www-form-urlencoded"
  Body = @{
    grant_type = "authorization_code"
    client_id = $env:COGNITO_CLIENT_ID
    code = $authorizationCode
    redirect_uri = $redirectUri
    code_verifier = $codeVerifier
  }
}

$tokenResponse = Invoke-RestMethod @tokenRequest

if (-not $tokenResponse.access_token) {
  throw "Cognito did not return an access token."
}

Write-Host "Access token received. Expires in $($tokenResponse.expires_in) seconds."
Write-Host "Token type: $($tokenResponse.token_type)"
~~~

redirect_uri trong token request phải giống chính xác redirect_uri ở authorization request. Cognito chỉ trả token khi code_verifier tạo ra đúng code_challenge ban đầu. Public app client không gửi client secret.

Token response thường có access_token, id_token, refresh_token, expires_in và token_type. Giữ token trong biến hoặc secure storage phù hợp; không in token ra terminal history hoặc log chia sẻ.

## 19. Gọi API bằng access token

Đặt API URL theo Invoke URL và route đã tạo:

~~~powershell
$apiUrl = "https://<api-id>.execute-api.<region>.amazonaws.com/orders"
$apiRequest = @{
  Method = "Get"
  Uri = $apiUrl
  Headers = @{
    Authorization = "Bearer $($tokenResponse.access_token)"
  }
}
$apiResponse = Invoke-RestMethod @apiRequest
$apiResponse | ConvertTo-Json -Depth 5
~~~

Kết quả thành công có dạng:

~~~json
{
  "message": "Request được Cognito JWT Authorizer chấp nhận",
  "method": "GET",
  "path": "/orders",
  "subject": "a1b2c3d4-example",
  "username": "lab-user",
  "token_use": "access",
  "scopes": [
    "openid",
    "email",
    "profile",
    "https://api.example.com/orders.read"
  ]
}
~~~

Giá trị subject, username và scopes sẽ khác theo user và token thực tế. API Gateway đã kiểm tra token trước khi Lambda được gọi.

## 20. Kiểm thử request không có token

Gửi request không có Authorization header:

~~~powershell
try {
  Invoke-WebRequest -Method Get -Uri $apiUrl
} catch {
  Write-Host "HTTP status:" $_.Exception.Response.StatusCode.value__
}
~~~

Kết quả mong đợi là 401 Unauthorized vì JWT Authorizer không nhận được token hợp lệ.

## 21. Kiểm thử access token thiếu scope

Chạy lại pkce-login.mjs nhưng chỉ yêu cầu OIDC scopes:

~~~powershell
$env:OAUTH_SCOPES = "openid email profile"
node .\pkce-login.mjs
~~~

Đăng nhập và đổi authorization code lấy token như các bước trước. Access token mới không có custom scope orders.read. Gọi GET /orders bằng access token này.

Kết quả mong đợi là 403 Forbidden hoặc lỗi authorization tương ứng vì token hợp lệ về chữ ký/issuer nhưng không có scope mà route yêu cầu.

Kiểm thử này chứng minh authentication và authorization là hai bước độc lập.

## 22. Kiểm thử ID token

Thử gọi API bằng ID token thay vì access token:

~~~powershell
$idTokenRequest = @{
  Method = "Get"
  Uri = $apiUrl
  Headers = @{
    Authorization = "Bearer $($tokenResponse.id_token)"
  }
}
Invoke-WebRequest @idTokenRequest
~~~

Route yêu cầu custom scope orders.read. ID token không mang custom API scope đó, vì vậy request phải bị từ chối ở bước scope authorization. Đây là lý do nên gắn authorization scopes vào route.

Nếu một route không cấu hình authorization scopes, JWT Authorizer có thể chấp nhận một JWT hợp lệ khác cùng issuer/audience, kể cả ID token nếu các claim phù hợp. Không bỏ qua yêu cầu scope cho route API chỉ vì chữ ký JWT hợp lệ.

## 23. Kiểm thử token sai issuer, audience hoặc hết hạn

Thử các tình huống trong môi trường lab:

- Gửi token từ một User Pool khác.
- Dùng token của app client khác.
- Thay đổi một ký tự trong token để làm sai chữ ký.
- Dùng token đã hết hạn.
- Dùng token không có custom scope.

Kết quả:

| Tình huống | Kết quả mong đợi |
|---|---|
| Không có token | 401 |
| Chữ ký sai | 401 |
| Issuer sai | 401 |
| Audience/client ID sai | 401 |
| Token hết hạn | 401 |
| Token hợp lệ nhưng thiếu scope | 403 |
| Token hợp lệ, đúng scope | 2xx từ integration |

Mã HTTP cụ thể có thể kèm response body khác nhau tùy API Gateway và cấu hình route. Đọc header WWW-Authenticate và CloudWatch logs khi cần điều tra.

## 24. API Gateway xác minh JWT như thế nào?

HTTP API JWT Authorizer thực hiện các bước chính:

1. Đọc token từ identity source, trong lab là Authorization header.
2. Decode JWT để đọc header và claims.
3. Tìm public key theo kid trong JWKS của issuer.
4. Kiểm tra thuật toán và chữ ký.
5. Kiểm tra iss khớp issuer cấu hình.
6. Kiểm tra aud hoặc client_id khớp audience.
7. Kiểm tra exp, nbf và iat.
8. Nếu route yêu cầu scope, kiểm tra token có ít nhất một scope được yêu cầu.
9. Chỉ khi pass mới chuyển claims tới integration.

Với Cognito User Pool, issuer thường có dạng:

~~~text
https://cognito-idp.<region>.amazonaws.com/<user-pool-id>
~~~

JWKS endpoint được công bố qua OpenID Connect discovery document. API Gateway lấy public key để xác minh token; ứng dụng không cần tải private key hoặc tự ký token.

## 25. Tự kiểm tra JWT claims an toàn

JWT có ba phần được phân tách bằng dấu chấm:

~~~text
header.payload.signature
~~~

Header thường có alg và kid. Payload có các claims như iss, sub, exp, iat, token_use, client_id và scope. Signature xác minh token được ký bởi private key tương ứng.

Decode payload chỉ giúp đọc nội dung, không xác minh chữ ký. Không được tin claim chỉ vì decode thành công. API Gateway Authorizer hoặc thư viện JWT có kiểm tra chữ ký, issuer, audience và expiration mới tạo ra kết quả xác minh.

Không gửi token production lên website debug JWT công khai. Token bearer có thể cho phép người khác thực hiện request thay user cho tới khi hết hạn hoặc bị hệ thống kiểm tra trạng thái thu hồi.

## 26. Cấu hình nhiều route theo quyền

Khi API lớn hơn, chia route theo action:

| Route | Scope | Ý nghĩa |
|---|---|---|
| GET /orders | https://api.example.com/orders.read | Xem đơn hàng |
| GET /orders/{id} | https://api.example.com/orders.read | Xem chi tiết |
| POST /orders | https://api.example.com/orders.write | Tạo đơn |
| PATCH /orders/{id} | https://api.example.com/orders.write | Cập nhật đơn |

Mỗi route có thể dùng cùng JWT Authorizer nhưng có authorization scopes riêng. Một access token có cả read và write có thể gọi cả hai nhóm route; token chỉ có read không được gọi write.

Không dùng scope thay thế authorization theo tài nguyên. Ví dụ user có orders.read nhưng chỉ được xem đơn thuộc tenant của mình; Lambda/service layer vẫn phải kiểm tra tenantId hoặc ownership theo dữ liệu đã xác thực.

## 27. Bảo vệ Lambda và backend

JWT Authorizer giúp chặn request không hợp lệ trước Lambda, nhưng backend vẫn cần:

- Kiểm tra tenant, ownership và business rules.
- Không tin các header do client tự gửi để xác định user nếu chúng không được gateway tạo/kiểm soát.
- Chỉ đọc identity claims từ requestContext.authorizer.jwt.
- Dùng IAM execution role tối thiểu cho Lambda.
- Giới hạn Lambda invoke permission cho đúng API Gateway source ARN.
- Không trả stack trace, secret hoặc nội dung exception ra client.
- Ghi correlation/request ID để điều tra.
- Bảo vệ database bằng IAM, secret rotation và network isolation phù hợp.

Nếu backend có thể được gọi trực tiếp ngoài API Gateway, cần thêm cơ chế bảo vệ ở đường gọi đó. Không giả định mọi request tới Lambda đều đã đi qua JWT Authorizer.

## 28. Token expiration, refresh và revocation

Access token có thời hạn ngắn hơn refresh token. Khi access token hết hạn, ứng dụng có thể dùng refresh token để lấy token mới theo cấu hình app client.

Các điểm quan trọng:

- Đặt access token lifetime theo mức rủi ro và trải nghiệm ứng dụng.
- Lưu refresh token trong secure storage; không đưa vào URL hoặc log.
- Bật token revocation cho app client; app client mới hiện bật mặc định.
- Dùng RevokeToken, revoke endpoint, GlobalSignOut hoặc AdminUserGlobalSignOut theo nhu cầu.
- Xóa token khỏi client storage khi logout.

Giới hạn quan trọng: JWT là self-contained. Token đã bị Cognito revoke vẫn có thể vượt qua một bộ xác minh offline chỉ kiểm tra chữ ký và expiration. API Gateway JWT Authorizer xác minh JWT theo issuer keys và claims; nó không truy vấn Cognito để kiểm tra trạng thái revoke trên từng request. Vì vậy, revocation có thể không chặn ngay một access token đang còn hạn ở API Gateway.

Nếu cần thu hồi hiệu lực gần như tức thời, cân nhắc access token lifetime ngắn, denylist/session state do backend kiểm tra, hoặc authorizer tùy chỉnh có bước kiểm tra trạng thái. Cần đánh đổi thêm latency, chi phí và độ phức tạp.

## 29. CORS cho ứng dụng chạy trên browser

Lab gọi API bằng PowerShell nên không cần CORS. Khi frontend JavaScript chạy từ một origin khác, cấu hình CORS trên HTTP API:

- Allowed origins: chỉ domain frontend thực tế.
- Allowed methods: GET/POST/PATCH theo route.
- Allowed headers: Authorization và Content-Type.
- Expose headers nếu frontend cần đọc header response.

Không dùng wildcard origin cho ứng dụng có credential hoặc dữ liệu nhạy cảm nếu không có lý do rõ ràng. CORS không phải cơ chế authentication/authorization; nó chỉ là chính sách browser kiểm soát việc JavaScript đọc response cross-origin.

## 30. Troubleshooting

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| redirect_mismatch | Callback URL không khớp cấu hình app client | So sánh redirect_uri từng ký tự ở authorize và token request |
| invalid_grant | Authorization code hết hạn/đã dùng hoặc PKCE verifier sai | Tạo flow mới và đổi code một lần với verifier đúng |
| invalid_client | Sai client ID hoặc app client yêu cầu secret | Dùng public client không secret cho PKCE browser flow |
| unauthorized_client | Authorization code grant chưa bật | Bật authorization code grant trong app client |
| 401 Unauthorized | Issuer, audience, chữ ký hoặc expiration không đúng | Decode claims để kiểm tra, sau đó xác minh issuer/audience và JWKS |
| 403 Forbidden | Token hợp lệ nhưng thiếu custom scope | Yêu cầu scope đúng ở authorize URL và gắn vào app client |
| Token không có custom scope | Scope chưa gắn vào app client hoặc dùng InitiateAuth | Gắn custom scope và dùng OAuth authorization endpoint |
| Lambda không được gọi | JWT Authorizer từ chối hoặc route chưa gắn integration | Kiểm tra authorizer, route và execution logs |
| Lambda trả 500 | Handler sai hoặc Lambda execution role thiếu quyền | Kiểm tra CloudWatch Logs và function configuration |
| API trả 502 | API Gateway không invoke được Lambda hoặc response format sai | Kiểm tra Lambda permission, integration và payload format |
| Domain không truy cập được | Domain chưa hoàn tất provisioning hoặc sai hostname | Kiểm tra trạng thái domain và Region |
| State mismatch | Callback không thuộc login flow vừa tạo | Từ chối response, chạy lại PKCE flow |

Khi API trả 401, kiểm tra WWW-Authenticate header để biết token thiếu audience, sai issuer hoặc invalid token. Không ghi access token nguyên văn vào ticket để debug.

## 31. Kiểm tra kết quả lab

- [ ] User Pool đã tạo và có User Pool ID.
- [ ] Resource server có custom scopes orders.read và orders.write.
- [ ] Public app client không có client secret.
- [ ] Authorization code grant và PKCE được cấu hình.
- [ ] Callback URL localhost được đăng ký chính xác.
- [ ] Managed login domain hoạt động.
- [ ] User thử nghiệm đăng nhập thành công.
- [ ] Lambda backend trả claims đã xác minh.
- [ ] HTTP API JWT Authorizer có đúng issuer và audience.
- [ ] GET /orders yêu cầu orders.read.
- [ ] Request không token trả 401.
- [ ] Token thiếu scope bị từ chối.
- [ ] Access token có đúng scope gọi API thành công.
- [ ] ID token không được dùng thay access token cho route có custom scope.
- [ ] Không có token hoặc secret trong log/source control.

## 32. Dọn dẹp tài nguyên

Sau khi hoàn thành:

1. Xóa API Gateway HTTP API.
2. Xóa Lambda function orders-api-lab.
3. Xóa User Pool domain nếu không dùng lại.
4. Xóa User Pool và app client thử nghiệm.
5. Xóa IAM role chỉ được tạo cho Lambda lab nếu không còn function nào sử dụng.
6. Kiểm tra CloudWatch log groups và xóa log lab nếu không cần lưu.

Không xóa User Pool, IAM role hoặc API đang được ứng dụng khác sử dụng. Kiểm tra resource name và owner trước khi xóa.

## 33. Mở rộng sau lab

Sau khi luồng cơ bản hoạt động, có thể mở rộng:

- Thêm POST /orders với orders.write.
- Thêm group/tenant claims và kiểm tra quyền theo tài nguyên.
- Kết nối identity provider bên ngoài như Google hoặc enterprise OIDC.
- Dùng custom domain và HTTPS callback cho frontend.
- Dùng AWS Verified Permissions nếu cần policy-based authorization phức tạp.
- Dùng Lambda authorizer nếu cần kiểm tra claims hoặc trạng thái phiên tùy chỉnh.
- Thêm CloudWatch alarms, access logs và tracing.
- Thêm rate limiting, WAF và abuse protection cho API public.

## 34. Ghi nhớ

Cognito User Pool xác thực người dùng và phát hành ID/access/refresh tokens. Resource server định nghĩa custom scopes trong access token. Public app client nên dùng Authorization Code Grant với PKCE và không giữ client secret trong browser/mobile app.

API Gateway HTTP API JWT Authorizer kiểm tra chữ ký, issuer, audience/client ID, thời hạn và scope trước khi gọi backend. Route có authorization scopes giúp phân biệt token có quyền API với JWT chỉ chứng minh user đã đăng nhập. Lambda tiếp tục kiểm tra ownership, tenant và business rules.

JWT revocation không đồng nghĩa mọi API offline validator sẽ biết token bị thu hồi ngay. Chọn access token lifetime và cơ chế kiểm tra session theo yêu cầu bảo mật. Luôn giữ token khỏi log, URL và source control.

## Tài liệu tham khảo

- [Using PKCE in Authorization Code Grants - Amazon Cognito](https://docs.aws.amazon.com/cognito/latest/developerguide/using-pkce-in-authorization-code.html)
- [Application-specific Settings with App Clients - Amazon Cognito](https://docs.aws.amazon.com/cognito/latest/developerguide/user-pool-settings-client-apps.html)
- [Scopes, M2M, and Resource Servers - Amazon Cognito](https://docs.aws.amazon.com/cognito/latest/developerguide/cognito-user-pools-define-resource-servers.html)
- [OAuth 2.0 Grants - Amazon Cognito](https://docs.aws.amazon.com/cognito/latest/developerguide/federation-endpoints-oauth-grants.html)
- [Understanding User Pool JSON Web Tokens](https://docs.aws.amazon.com/cognito/latest/developerguide/amazon-cognito-user-pools-using-the-access-token.html)
- [Verifying JSON Web Tokens - Amazon Cognito](https://docs.aws.amazon.com/cognito/latest/developerguide/amazon-cognito-user-pools-using-tokens-verifying-a-jwt.html)
- [Control Access to HTTP APIs with JWT Authorizers - API Gateway](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-jwt-authorizer.html)
- [Troubleshoot HTTP API JWT Authorizers](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-troubleshooting-jwt.html)
- [Create an HTTP API - API Gateway](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api.html)
- [Create Lambda Proxy Integrations for HTTP APIs](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-develop-integrations-lambda.html)
- [Ending User Sessions with Token Revocation - Amazon Cognito](https://docs.aws.amazon.com/cognito/latest/developerguide/token-revocation.html)
- [Control Access to REST APIs with Cognito User Pools](https://docs.aws.amazon.com/apigateway/latest/developerguide/apigateway-integrate-with-cognito.html)
