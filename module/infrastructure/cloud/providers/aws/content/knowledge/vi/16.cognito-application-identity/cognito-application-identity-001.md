# Phân biệt Cognito User Pool và Identity Pool

Một ứng dụng bán hàng có thể cần cho khách hàng **đăng ký, đăng nhập bằng email, Google hoặc tài khoản doanh nghiệp**, sau đó gọi API để xem đơn hàng. Một ứng dụng ảnh khác lại muốn người dùng đã đăng nhập **tải ảnh trực tiếp từ Amazon S3** mà không phải đưa toàn bộ lưu lượng qua máy chủ trung gian. Cả hai có thể sử dụng **Amazon Cognito**, nhưng không phải cùng một thành phần.

**Amazon Cognito User Pool** tập trung vào **đăng ký, xác thực người dùng, quản lý hồ sơ đăng nhập và phát hành các token OIDC/OAuth 2.0**. **Amazon Cognito Identity Pool** tập trung vào **liên kết danh tính từ một nhà cung cấp đã tin cậy với IAM role để cấp AWS credentials tạm thời**. Hai dịch vụ có thể **hoạt động độc lập** hoặc **được kết hợp**; không phải ứng dụng nào sử dụng User Pool cũng cần Identity Pool.

Bài thuộc chương **Danh tính ứng dụng với Cognito** của mô-đun **CLOUD_PROVIDERS_AWS**. Nội dung gắn việc thiết kế danh tính ứng dụng với Region/AZ, IAM, VPC, compute, lưu trữ, database, tích hợp và serverless. Người học sẽ rèn khả năng chọn dịch vụ, bảo vệ API và dữ liệu, giám sát, phục hồi và kiểm soát chi phí.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích vai trò của **User Pool**, **Identity Pool**, **App Client**, **Identity Provider (IdP)**, **JWT** và **IAM role**.
2. Phân biệt **xác thực (authentication)**, **ủy quyền ứng dụng (authorization)** và **cấp quyền AWS bằng IAM**.
3. Chọn **chỉ User Pool**, **chỉ Identity Pool** hoặc **cả hai** theo nhu cầu nghiệp vụ.
4. Hiểu ba loại token của User Pool: **ID token, access token, refresh token**; biết token nào dùng ở API và token nào đưa vào Identity Pool.
5. Mô tả luồng **User Pool ID token → Identity Pool GetId/GetCredentialsForIdentity → STS credentials → AWS API**.
6. Đọc IAM role trust policy có điều kiện **aud/amr**, thiết kế authenticated/guest role và quyền tối thiểu.
7. Áp dụng nguyên tắc **Authorization Code + PKCE**, JWT verification, MFA và bảo vệ tokens/secrets.
8. Chẩn đoán những lỗi phổ biến giữa Cognito, API Gateway, IAM và S3; tính chi phí và xây checklist production.

## 2. Năm khái niệm cần tách biệt ngay từ đầu

| Khái niệm | Trả lời câu hỏi nào? | Ví dụ |
|---|---|---|
| **Authentication** | Người dùng này là ai và đã chứng minh danh tính chưa? | Đăng nhập với password, passkey, MFA hoặc IdP bên ngoài |
| **Application authorization** | Người dùng được thực hiện nghiệp vụ gì? | Chỉ chủ đơn hàng được xem đơn của mình; quản trị viên được quản lý sản phẩm |
| **AWS IAM authorization** | Principal được gọi API AWS nào và trên tài nguyên nào? | Cho phép s3:GetObject trên prefix của người dùng |
| **User Pool** | Ai quản lý tài khoản đăng nhập, phiên đăng nhập và token? | User Pool phát hành access/ID/refresh tokens |
| **Identity Pool** | Từ danh tính đã có, ứng dụng nhận quyền AWS tạm thời nào? | Identity Pool cấp credentials thông qua IAM role |

**Đăng nhập thành công không đồng nghĩa được phép đọc mọi dữ liệu.** Một access token hợp lệ chỉ chứng minh điều kiện cấp token và những quyền ở mức claims/scopes mà bạn đã thiết kế. Backend vẫn cần kiểm tra quyền trên **từng đơn hàng, tenant, file và thao tác**.

**Identity Pool cũng không phải nơi lưu mật khẩu thay User Pool.** Nó có thể tin cậy User Pool hoặc các IdP được hỗ trợ, rồi kết nối danh tính với quyền IAM. Tên chung “Cognito” dễ khiến hai trách nhiệm bị gộp làm một, dẫn tới các lỗi bảo mật.

## 3. Bảng so sánh User Pool và Identity Pool

| Tiêu chí | Cognito **User Pool** | Cognito **Identity Pool** |
|---|---|---|
| Mục đích chính | **Đăng ký, đăng nhập, liên kết IdP, phát hành token** | **Liên kết danh tính và nhận AWS credentials tạm thời** |
| Đối tượng quản lý | User directory, profile attributes, groups, app clients | Federated identity IDs, identity providers, authenticated/guest roles, role mappings |
| Dữ liệu xác thực | Password/challenge, IdP federation, MFA/passkey theo tính năng | Dùng bằng chứng đăng nhập từ IdP; có thể hỗ trợ khách **chưa đăng nhập** |
| Kết quả thông thường | **ID JWT, access JWT, refresh token** | **AWS temporary credentials** và **IdentityId** |
| Chuẩn/đích sử dụng | OAuth 2.0, OpenID Connect, sign-in và API authorization | IAM role, STS web identity, ký yêu cầu AWS SigV4 |
| Tích hợp API Gateway | JWT/User Pool authorizer xác thực token | IAM authorization qua credentials nếu API được cấu hình dùng AWS_IAM |
| Dùng trực tiếp với S3/DynamoDB | User Pool token **không tự** là AWS access key | Có thể gọi AWS SDK với credentials quyền hạn tối thiểu |
| Guest/unauthenticated | Không phải mục tiêu của một User Pool session đăng nhập | Có tùy chọn **unauthenticated identities** khi bật rõ ràng |
| Cần dùng cùng nhau? | Không | Không; cũng có thể dùng IdP ngoài mà không có User Pool |
| Định danh dễ thấy | User Pool ID dạng **region_...**, app client ID | Identity Pool ID dạng **region:UUID** |
| Kiểm soát truy cập | OAuth scopes, JWT claims/groups và kiểm tra ở API | IAM policies, trust policies, role mappings/ABAC |

**Ghi nhớ bằng một câu:** User Pool cho biết **ai đăng nhập và token nào chứng minh điều đó**; Identity Pool cho biết **ứng dụng được nhận AWS credentials với những quyền IAM nào**. Không dùng chúng thay thế lẫn nhau.

### 3.1. Ví dụ chọn nhanh

- Website đặt hàng có API Java/Lambda riêng: **User Pool** có thể đã đủ; API kiểm tra access token và quyền từng order.
- Ứng dụng mobile tải tài nguyên cá nhân trực tiếp từ S3: có thể dùng **User Pool + Identity Pool**, với role chỉ cho phép prefix đúng.
- Ứng dụng chỉ có **Google/OIDC** là IdP và cần AWS credentials cho client: có thể dùng **Identity Pool** liên kết trực tiếp IdP mà **không cần User Pool** nếu thỏa yêu cầu.
- Phần nội dung public đặt trên CloudFront: không mặc định cần cả hai; cân nhắc CDN public hoặc signed URLs/cookies theo mô hình truy cập.
- Backend Lambda gọi DynamoDB với quyền dịch vụ: thường dùng **Lambda execution role**, **không** cần Identity Pool để cấp quyền cho backend.

## 4. User Pool: danh bạ người dùng và nhà phát hành token

### 4.1. Những thành phần trong User Pool

Một **User Pool** chứa hoặc liên kết hồ sơ người dùng và cấu hình xác thực. Những thành phần thường gặp:

| Thành phần | Vai trò |
|---|---|
| **User directory** | User attributes như username, email, phone, trạng thái xác minh |
| **App Client** | Ứng dụng tích hợp User Pool, OAuth grant types, redirect URIs, scopes, thời hạn token |
| **Managed login / Hosted UI** | Giao diện đăng nhập được Cognito quản lý theo cấu hình |
| **Domain** | Endpoint cho OAuth/OIDC authorize/token/logout và các liên kết phù hợp |
| **Identity provider federation** | Google, Apple, SAML/OIDC IdP được cấu hình |
| **MFA và account recovery** | Các bước bổ sung bảo vệ tài khoản và khôi phục |
| **Groups và custom attributes** | Thông tin nhóm/thuộc tính phục vụ quy tắc truy cập |
| **Lambda triggers** | Tùy biến một số bước đăng ký/đăng nhập/token theo trigger được hỗ trợ |

User Pool có thể lưu người dùng đăng ký trực tiếp hoặc liên kết danh tính từ một IdP khác; trong federation, Cognito có thể chuyển các claims của IdP thành hồ sơ và token của chính User Pool. Ứng dụng nhìn thấy **issuer User Pool** thay vì tự xử lý mọi cách đăng nhập.

### 4.2. Public app client so với confidential app client

- **Public client**: ứng dụng chạy trong browser/mobile không thể giữ bí mật an toàn. **Không nhúng client secret** vào JavaScript bundle hoặc ứng dụng mobile.
- **Confidential client**: backend/server-side app có khả năng bảo vệ client secret theo kiến trúc. Nó có thể dùng những OAuth grant types yêu cầu xác thực client.

Với SPA/mobile, thực hành tốt là **OAuth 2.0 Authorization Code Flow + PKCE (S256)**, kiểm tra **state** và **nonce** khi phù hợp, redirect URI chính xác và HTTPS. PKCE giúp ngăn đối tượng khác đổi một authorization code bị đánh cắp lấy tokens; nó **không thay thế** kiểm tra token và quyền backend.

### 4.3. Sơ đồ đăng nhập bằng User Pool

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant APP as Web / Mobile App
    participant UP as Cognito User Pool
    participant API as API Gateway / Backend
    U->>APP: Mở màn hình đăng nhập
    APP->>UP: /oauth2/authorize + PKCE + state
    UP->>U: Xác thực, MFA / IdP nếu có
    UP-->>APP: Authorization code qua callback
    APP->>UP: /oauth2/token + code_verifier
    UP-->>APP: ID token, access token, refresh token
    APP->>API: Authorization: Bearer ACCESS_TOKEN
    API->>API: Verify signature, issuer, client, exp, scopes
    API-->>APP: Kết quả nghiệp vụ đã kiểm tra quyền
~~~

Ví dụ này **không cần Identity Pool**. API Gateway có thể kiểm tra JWT trước khi chuyển request tới backend, nhưng backend vẫn phải kiểm tra **object-level authorization**, chẳng hạn đơn hàng thuộc đúng người dùng/tenant.

## 5. Ba token của User Pool: không được dùng nhầm

| Token | Dạng | Mục đích đúng | Không được hiểu nhầm |
|---|---|---|---|
| **ID token** | JWT có chữ ký | Thông tin danh tính cho ứng dụng; **bằng chứng đăng nhập khi liên kết User Pool với Identity Pool** | Không phải AWS AccessKeyId; không mặc nhiên thay API access token |
| **Access token** | JWT có chữ ký | Gọi API và hành động được phép theo OAuth scopes/claims; một số API self-service Cognito | Không phải IAM session credentials |
| **Refresh token** | Token opaque | Xin cấp lại ID/access tokens theo thời hạn và cơ chế refresh | Không phải JWT để gửi cho API hoặc đưa vào Identity Pool |

### 5.1. ID token chứa gì?

Ví dụ cấu trúc claims rút gọn, **không phải token thật**:

~~~json
{
  "iss": "https://cognito-idp.ap-southeast-1.amazonaws.com/ap-southeast-1_EXAMPLE",
  "sub": "11111111-2222-3333-4444-555555555555",
  "aud": "APP_CLIENT_ID",
  "token_use": "id",
  "email_verified": true,
  "exp": 1900000000
}
~~~

Giá trị **sub** ở đây là **User Pool user subject**. Nó không đồng nhất với **IdentityId** của Identity Pool. Nếu app cần liên kết hai loại ID, hãy duy trì mapping an toàn và tránh coi địa chỉ email là khóa bất biến.

### 5.2. Access token chứa gì?

Ví dụ claims rút gọn:

~~~json
{
  "iss": "https://cognito-idp.ap-southeast-1.amazonaws.com/ap-southeast-1_EXAMPLE",
  "sub": "11111111-2222-3333-4444-555555555555",
  "client_id": "APP_CLIENT_ID",
  "token_use": "access",
  "scope": "openid orders/read",
  "exp": 1900000000
}
~~~

API dùng **access token** cho bài toán OAuth scopes, chẳng hạn **orders/read**, khi cấu hình resource server/scopes phù hợp. Trong nhiều luồng User Pool, **aud** có trong ID token, còn access token thường chứa **client_id**; access token được ràng buộc với resource server có thể có aud riêng. Hãy kiểm tra theo token type và cấu hình thật, không viết một parser giả định hai loại token luôn có claims giống nhau.

### 5.3. Làm thế nào để xác minh JWT an toàn?

Khi backend tự xác minh JWT:

1. Đọc token từ đường truyền **HTTPS** và giới hạn kích thước hợp lý; **không tin claims trước khi verify**.
2. Kiểm tra **signature RS256** bằng public keys tại **JWKS endpoint** của đúng User Pool, tra **kid** và xử lý key rotation.
3. Kiểm tra **iss** khớp User Pool mong đợi; kiểm tra **exp**, **token_use** và thời gian liên quan.
4. Kiểm tra **aud** của ID token hoặc **client_id/audience** của access token theo hợp đồng bảo mật.
5. Với API, xác minh **scope**, group/role và **quyền ở mức tài nguyên** tương ứng request.
6. Có chính sách hết hạn/revocation; JWT kiểm tra offline có thể vẫn hợp lệ về chữ ký và exp dù token đã bị thu hồi trước thời hạn.

JWKS thường có URL dạng:

~~~text
https://cognito-idp.ap-southeast-1.amazonaws.com/ap-southeast-1_EXAMPLE/.well-known/jwks.json
~~~

**Chỉ giải mã Base64 của JWT để xem payload không phải xác minh token.** Tuyệt đối không ra quyết định quyền dựa trên JWT chưa xác minh. API Gateway HTTP API JWT authorizer có thể xác minh JWT thay ứng dụng ở lớp gateway; với các route cần quyền, nên cấu hình **authorization scopes** để tránh chấp nhận nhầm ID token khi route phải yêu cầu access token.

### 5.4. Refresh và lưu trữ token

ID/access tokens thường có thời hạn ngắn; refresh token sống lâu hơn tùy cấu hình app client và có thể áp dụng rotation. Với browser, cân nhắc **backend-for-frontend (BFF)** cùng cookies **HttpOnly/Secure/SameSite** hoặc một phương án lưu token hạn chế XSS phù hợp. Với native mobile, dùng secure storage của hệ điều hành. Không lưu refresh token hoặc client secret trong log, URL, analytics hay mã nguồn.

**Access token không dùng để lấy AWS STS credentials trực tiếp** trong luồng chuẩn ghép Cognito User Pool với Identity Pool. Tại Identity Pool, bằng chứng từ **User Pool là ID token**, theo tài liệu của AWS.

## 6. Identity Pool: danh tính liên kết và AWS credentials tạm thời

**Cognito Identity Pool** còn gọi là **federated identities**. Dịch vụ cho phép ứng dụng dùng bằng chứng xác thực từ một IdP được hỗ trợ để nhận **IdentityId** và **temporary AWS credentials**. Identity Pool chọn role theo cấu hình để giới hạn quyền đối với S3, DynamoDB, API Gateway với IAM authorization hoặc các AWS services khác.

### 6.1. Các IdP mà Identity Pool có thể tin cậy

Identity Pool có thể tích hợp:

- **Cognito User Pool** và ID token được cấp sau đăng nhập.
- Các **OIDC identity providers** tương thích.
- Các **SAML 2.0 identity providers** và assertion phù hợp.
- Một số **social identity providers** theo loại token được hỗ trợ.
- **Developer authenticated identities** do một backend đáng tin cậy chịu trách nhiệm chứng minh danh tính.
- **Unauthenticated (guest) identities** nếu được bật, không cần đăng nhập trước.

**Không bắt buộc phải tạo User Pool nếu Identity Pool đã nhận một IdP được hỗ trợ trực tiếp** và ứng dụng không cần User Pool quản lý account/flows. Ngược lại, nếu chỉ cần JWT cho API do backend kiểm soát, không cần tạo Identity Pool chỉ vì ứng dụng dùng Cognito.

### 6.2. Enhanced authentication flow

Luồng thường được khuyến nghị là **enhanced/simplified**:

1. Ứng dụng nhận bằng chứng xác thực từ IdP, ví dụ **User Pool ID token**.
2. Ứng dụng gọi **GetId** với Identity Pool ID và **Logins** map.
3. Identity Pool trả về **IdentityId** tương ứng.
4. Ứng dụng gọi **GetCredentialsForIdentity** với IdentityId và bằng chứng xác thực.
5. Identity Pool chọn IAM role theo role mappings và làm việc với AWS STS để trả **credentials tạm thời**.
6. AWS SDK dùng **AccessKeyId + SecretAccessKey + SessionToken** để ký yêu cầu đến S3, DynamoDB hoặc dịch vụ được cấp quyền.

~~~mermaid
sequenceDiagram
    participant APP as Mobile / Browser
    participant UP as User Pool
    participant IP as Identity Pool
    participant STS as AWS STS
    participant S3 as Amazon S3
    APP->>UP: Login / OAuth code + PKCE
    UP-->>APP: ID token + access/refresh token
    APP->>IP: GetId + Logins[USER_POOL_PROVIDER] = ID token
    IP-->>APP: IdentityId
    APP->>IP: GetCredentialsForIdentity + ID token
    IP->>STS: Chọn IAM role / web identity
    STS-->>IP: Temporary AWS credentials
    IP-->>APP: AccessKeyId + SecretAccessKey + SessionToken + Expiration
    APP->>S3: SigV4 request bằng credentials tạm thời
    S3-->>APP: Object khi IAM và resource policies đều cho phép
~~~

Ứng dụng nên sử dụng **AWS SDK hoặc AWS Amplify credentials provider** phù hợp thay vì tự lưu và ký credentials thủ công. SDK có thể quản lý cấp mới/refresh temporary credentials theo cơ chế đã cấu hình. **Không** copy temporary credentials vào localStorage, log hoặc hard-code; mặc dù có expiration, chúng vẫn có quyền AWS thật trong thời gian còn hạn.

### 6.3. Logins map đúng định dạng cho User Pool

Khi tích hợp User Pool với Identity Pool, **provider name/key** trong Logins map có dạng:

~~~text
cognito-idp.ap-southeast-1.amazonaws.com/ap-southeast-1_EXAMPLE
~~~

Khác với issuer JWT ở trên, key này **không có tiền tố https://**. Ví dụ payload khái niệm cho GetId:

~~~json
{
  "IdentityPoolId": "ap-southeast-1:11111111-2222-3333-4444-555555555555",
  "Logins": {
    "cognito-idp.ap-southeast-1.amazonaws.com/ap-southeast-1_EXAMPLE": "ID_TOKEN_FROM_USER_POOL"
  }
}
~~~

**ID_TOKEN_FROM_USER_POOL** là placeholder, không phải token có thể dùng. Identity Pool phải đăng ký **đúng User Pool và App Client ID** trong cấu hình identity providers. Dùng access token thay ID token ở Logins cho User Pool, sai Region, sai provider key hoặc sai app client có thể dẫn đến lỗi xác thực.

### 6.4. IdentityId không phải User Pool sub

| Định danh | Phạm vi | Ví dụ |
|---|---|---|
| **User Pool sub** | Người dùng trong một User Pool | UUID dạng 11111111-... |
| **User Pool ID** | User directory/auth issuer | ap-southeast-1_EXAMPLE |
| **App Client ID** | Ứng dụng OAuth/OIDC | APP_CLIENT_ID |
| **Identity Pool ID** | Identity Pool được cấu hình | ap-southeast-1:11111111-... |
| **IdentityId** | Federated identity do Identity Pool trả về | ap-southeast-1:aaaaaaaa-... |
| **IAM role ARN** | Nhóm quyền AWS có thể được cấp cho danh tính | arn:aws:iam::111122223333:role/app-user-role |

**Không lấy User Pool sub để thay trực tiếp IdentityId**. Chúng thuộc hai hệ định danh; khi áp dụng IAM policy variables cho Identity Pool, giá trị nhận diện có thể là Identity Pool identity ID, không phải User Pool subject.

## 7. IAM role, role mapping và guest access trong Identity Pool

Identity Pool không tự cấp tất cả quyền AWS. Nó liên kết một danh tính với **IAM role** và các chính sách phù hợp; quyền cuối cùng còn bị giới hạn bởi resource policy, KMS policy, permission boundary, SCP và những cơ chế kiểm soát có hiệu lực khác.

### 7.1. Authenticated role và unauthenticated role

| Role | Ai có thể nhận? | Nguyên tắc |
|---|---|---|
| **Authenticated role** | Danh tính đã xác thực qua provider được Identity Pool chấp nhận | Chỉ cấp AWS actions tối thiểu theo nghiệp vụ |
| **Unauthenticated (guest) role** | Người chưa đăng nhập, **nếu guest access được bật** | Chỉ cấp quyền mà tổ chức sẵn sàng công khai cho bất kỳ ai |
| **Role theo claims/rules/groups** | Danh tính có thông tin phù hợp role mapping | Kiểm tra từng role được chọn, xử lý claim thiếu và đa role |

**Bật guest access nghĩa là người không đăng nhập vẫn có thể nhận temporary AWS credentials với quyền của guest role.** Không được coi Identity Pool ID là mật khẩu hay thông tin bí mật; bất kỳ ai biết cấu hình công khai và có thể kết nối dịch vụ đều có thể cố sử dụng quyền guest được cấp. Tắt guest nếu ứng dụng không cần, hoặc chỉ cho phép đọc rất ít tài nguyên.

### 7.2. IAM trust policy phải ràng buộc đúng Identity Pool

Role trust policy xác định **ai được assume role**, khác với policy xác định **role được gọi AWS API nào**. Với enhanced flow, Identity Pool sử dụng STS liên quan đến **AssumeRoleWithWebIdentity**. Role cần trust principal **cognito-identity.amazonaws.com** và ràng buộc **aud = đúng Identity Pool ID**; nên kèm điều kiện **amr = authenticated** hoặc **unauthenticated** tùy role.

Ví dụ trust policy cho **authenticated role** (các ID chỉ để minh họa):

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowOnlyAuthenticatedIdentitiesFromThisPool",
      "Effect": "Allow",
      "Principal": {
        "Federated": "cognito-identity.amazonaws.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "cognito-identity.amazonaws.com:aud": "ap-southeast-1:11111111-2222-3333-4444-555555555555"
        },
        "ForAnyValue:StringLike": {
          "cognito-identity.amazonaws.com:amr": "authenticated"
        }
      }
    }
  ]
}
~~~

**aud ở trust policy này là Identity Pool ID**, không phải App Client ID hay **aud** của User Pool ID token. **amr** mô tả trạng thái xác thực và nguồn đăng nhập theo identity-pool token; với guest role, điều kiện cần khớp **unauthenticated**.

Không để trust policy chấp nhận **mọi identity pool**, hoặc bỏ điều kiện aud rồi dựa vào tên role để bảo mật. Trong **enhanced flow**, role được chọn theo Identity Pool configuration và cần tuân thủ điều kiện tài khoản/role của dịch vụ. **Basic/classic flow** có cách ứng dụng giao tiếp STS khác, nên không áp dụng máy móc cùng giả định role selection; ưu tiên enhanced flow khi không có yêu cầu đặc biệt.

### 7.3. Policy quyền S3 theo từng IdentityId

Ví dụ: mỗi người dùng đã đăng nhập chỉ được đọc những object trong prefix tương ứng identity của chính họ:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadObjectsInOwnIdentityPrefix",
      "Effect": "Allow",
      "Action": ["s3:GetObject"],
      "Resource": [
        "arn:aws:s3:::example-private-users/files/${cognito-identity.amazonaws.com:sub}/*"
      ]
    }
  ]
}
~~~

**IDENTITY_SUB_VAR** trong đường dẫn trên được thay bằng IAM policy variable của Identity Pool. IAM tự thế giá trị identity ID từ phiên được assume role; đây **không phải** một chuỗi do browser được quyền tùy ý gửi để mở rộng truy cập. Cần chuẩn bị cách tạo/di chuyển object keys theo prefix thực tế và kiểm tra quyền, bucket policy, S3 Block Public Access, KMS và Object Ownership.

Ví dụ chỉ có **s3:GetObject** nên không tự cấp **s3:ListBucket** hay **s3:PutObject**. Nếu ứng dụng phải upload, cần xây policy riêng cho prefix, kiểm tra object size, media type, malware scanning, CORS và các điều kiện S3 phù hợp. Người dùng không nên được cấp quyền quản trị bucket hoặc truy cập dữ liệu của người khác.

**Lưu ý kỹ thuật:** policy variable **cognito-identity.amazonaws.com:sub** là **Identity Pool identity ID**, không phải **sub** trong User Pool JWT. Nếu hệ thống backend sử dụng User Pool sub làm thư mục, cần mapping hoặc thiết kế quyền phù hợp thay vì ghép hai ID trực tiếp.

### 7.4. Role mapping từ claims của User Pool

Identity Pool có thể áp dụng **default authenticated role**, **rules based on claims** hoặc **token-based role mapping**. Khi kết hợp User Pool groups, token có thể mang những claims như **cognito:groups**, **cognito:roles** và **cognito:preferred_role** theo cấu hình; Identity Pool có thể dùng chúng để chọn role.

Ví dụ nhóm **premium** có quyền xem một bộ asset khác nhóm **standard**. Việc đặt người dùng vào group User Pool **không tự cấp quyền IAM**: cần role, trust policy, permission policy và role mapping tương ứng. Khi một token khớp nhiều role hoặc không có rule nào khớp, cấu hình **AmbiguousRoleResolution** quyết định dùng default role hay từ chối; phải kiểm thử để tránh fallback quá rộng.

**Đừng dùng nhóm Cognito làm cách thay thế mọi kiểm tra quyền nghiệp vụ.** Ví dụ **premium** chỉ nói gói khách hàng, không chứng minh người đó là chủ sở hữu của một hóa đơn cụ thể.

## 8. Ba mô hình kiến trúc cần phân biệt

### 8.1. Chỉ User Pool: ứng dụng tự bảo vệ API

~~~mermaid
flowchart LR
    U["Web / Mobile user"] --> UP["Cognito User Pool<br/>Sign-in + tokens"]
    UP -->|"Access JWT"| APP["Client application"]
    APP -->|"Bearer access JWT"| API["API Gateway JWT authorizer<br/>hoặc backend verify"]
    API --> L["Lambda / ECS / EC2"]
    L -->|"Execution / task role"| DB["DynamoDB / RDS / S3"]
~~~

Phù hợp khi client chỉ cần gọi **API của ứng dụng**. Backend giữ quyền truy cập AWS của chính backend; người dùng không cầm AWS access keys. API xác minh token và thực hiện **business authorization**, ví dụ lấy order theo **tenantId + ownerId**.

**Không cần Identity Pool** chỉ để API Gateway xác minh access JWT của User Pool.

### 8.2. Chỉ Identity Pool: đã có IdP khác hoặc guest

~~~mermaid
flowchart LR
    CLIENT["Mobile / Web client"] --> IDP["External OIDC / SAML / Social IdP<br/>hoặc guest identity"]
    IDP --> CLIENT
    CLIENT -->|"Provider proof hoặc guest"| IP["Cognito Identity Pool"]
    IP -->|"Temporary AWS credentials"| CLIENT
    CLIENT -->|"Signed AWS requests"| AWS["S3 / DynamoDB / AWS_IAM API"]
~~~

Phù hợp khi ứng dụng đã có IdP và chỉ cần **temporary AWS credentials** theo IAM, hoặc muốn cung cấp tài nguyên cho guest theo quyền thật sự tối thiểu. Trong thiết kế này **Identity Pool không cung cấp giao diện đăng nhập** cho IdP và không thay hệ thống quản lý mật khẩu người dùng.

### 8.3. Kết hợp cả hai: User Pool đăng nhập, Identity Pool cấp IAM

~~~mermaid
flowchart TB
    CLIENT["Mobile / SPA"] --> LOGIN["User Pool + app client<br/>Managed login / OAuth PKCE"]
    LOGIN --> TOKENS["ID token + access token"]
    TOKENS -->|"Access token"| API["API Gateway / App API"]
    TOKENS -->|"ID token"| IP["Cognito Identity Pool"]
    IP --> ROLE["IAM role + STS credentials"]
    ROLE -->|"SigV4"| S3["S3 private objects<br/>Scoped identity prefix"]
    API --> DB["Backend + database"]
~~~

Phù hợp khi cùng một client vừa gọi **API ứng dụng qua access token** vừa trực tiếp truy cập **một phần AWS resources qua identity-scoped credentials**. Hai loại thông tin xác thực cùng tồn tại nhưng có mục đích khác nhau.

### 8.4. Bảng quyết định nhanh

| Yêu cầu chính | User Pool | Identity Pool | Vì sao? |
|---|---|---|---|
| Login và bảo vệ REST API riêng | **Có** | Không bắt buộc | Access token/JWT authorizer là đủ cho nhiều API |
| Đăng nhập Google/SAML qua một issuer chung và hồ sơ người dùng | **Có** | Không bắt buộc | User Pool federates IdP, phát hành token |
| Browser nhận quyền IAM đọc object S3 theo người dùng | Thường có IdP | **Có** | Cần temporary AWS credentials và least-privilege role |
| AWS SDK client gọi DynamoDB trực tiếp theo IAM | Không bắt buộc | **Có** | Identity Pool liên kết IdP với temporary credentials |
| Chỉ phục vụ ảnh public từ S3 qua CloudFront | Không bắt buộc | Không bắt buộc | Dữ liệu public/cached không nhất thiết cần login |
| Backend Lambda gọi S3/DynamoDB | Không bắt buộc | Không bắt buộc | Dùng Lambda execution role cho backend |
| Guest đọc một tập asset có kiểm soát theo IAM | Không bắt buộc | Có thể có | Guest role chỉ cấp quyền an toàn với mọi khách |

## 9. API access và AWS resource access là hai cách ủy quyền

### 9.1. API Gateway + access token của User Pool

Một route **GET /orders/{id}** có thể yêu cầu access JWT với scope **orders/read**. JWT authorizer kiểm tra issuer/audience và signature; route scope cho biết yêu cầu có quyền ở mức API đã khai báo. Sau đó backend kiểm tra dữ liệu:

| Bước | Kiểm tra | Ai thực hiện? |
|---|---|---|
| 1 | Signature, issuer, expiry, audience/client và token type phù hợp | API Gateway authorizer hoặc backend |
| 2 | Scope **orders/read** cho route | JWT authorizer/backend |
| 3 | Order thuộc user/tenant trong token và người dùng được phép xem | Backend/authorization service |
| 4 | Truy vấn database và trả về trường được phép | Backend |

**JWT hợp lệ không cho phép xem đơn hàng của người khác.** Nếu backend chỉ kiểm tra signature rồi dùng **orderId** từ URL, người dùng có thể lợi dụng lỗi **broken object-level authorization (BOLA/IDOR)**. Identity Pool cũng không khắc phục được lỗi nghiệp vụ đó.

### 9.2. API Gateway AWS_IAM + Identity Pool credentials

Một API có thể được cấu hình **AWS_IAM**. Trong trường hợp đó, client dùng **temporary credentials** của Identity Pool và AWS SDK ký request theo **Signature Version 4 (SigV4)**, thay vì chỉ gửi **Bearer access JWT**. IAM policy cần cấp quyền **execute-api:Invoke** cho đúng API/stage/method/resource và resource policy/authorizer khác phải hợp lệ nếu có.

Chọn một mô hình authorization nhất quán cho từng route. Một route cấu hình AWS_IAM sẽ không tự chấp nhận Bearer JWT như yêu cầu IAM đã ký; ngược lại, một JWT authorizer không tự suy IAM role của khách hàng từ access token.

### 9.3. Direct S3 access: tiện lợi nhưng có trách nhiệm

Khi client gọi S3 trực tiếp bằng credentials Identity Pool:

- IAM policy, bucket policy, KMS và CORS phải đúng.
- Browser/app không cần được cấp quyền lớn hơn một prefix hoặc object cụ thể.
- API trực tiếp có thể giảm proxy traffic nhưng cần **client-side upload validation**, giới hạn kích thước/type, malware scanning và metadata controls.
- Với nhiều trường hợp **upload/download một lần**, backend cấp **presigned S3 URL** qua API đã xác thực có thể đơn giản hơn việc cấp AWS credentials cho từng client. Presigned URL phải có TTL, scope và quy trình thu hồi/kiểm soát phù hợp.

**Identity Pool không phải giải pháp bắt buộc cho mọi S3 upload.** So sánh direct credential flow với presigned URLs theo security posture, tần suất thao tác, dung lượng, khả năng offline và trải nghiệm người dùng.

## 10. Thiết kế User Pool và Identity Pool theo quy trình

### Bước 1 — Xác định người dùng, IdP và loại ứng dụng

Ai là người dùng: khách mua hàng, nhân viên, đối tác hay máy-máy? Ứng dụng web SPA, mobile hay backend confidential client? Có cần đăng ký tài khoản mới, MFA, password reset, social sign-in, enterprise SAML/OIDC và quản lý attributes không?

**Đầu ra:** quyết định có cần **User Pool** và các OAuth grant types/phương án xác thực phù hợp. Tránh dùng User Pool như một nơi cấp IAM access keys.

### Bước 2 — Phân loại cách truy cập tài nguyên

Liệt kê từng request:

- **Client → API ứng dụng**: thường dùng **User Pool access token**.
- **Client → S3/DynamoDB/AWS_IAM API trực tiếp**: cân nhắc **Identity Pool** hoặc presigned URL.
- **Backend → AWS services**: dùng **IAM execution/task/instance role**, không mượn credentials của người dùng nếu không có yêu cầu kiến trúc rõ.

**Đầu ra:** ma trận **principal × operation × resource × authorization method**, không quyết định theo tên dịch vụ được nhắc trong kiến trúc.

### Bước 3 — Cấu hình User Pool trước nếu cần đăng nhập

Tạo User Pool trong Region được chọn, cấu hình app client tương thích với public/confidential app, domain/managed login, redirect/logout URIs, sign-in methods, MFA, attributes, scopes và token durations. Với SPA/native app, dùng **Authorization Code + PKCE**; không nhúng client secret.

Nếu dùng IdP ngoài, cấu hình provider, claim mapping và thử các trường hợp thiếu email/đổi email. Tạo nhóm hoặc custom scopes khi có lý do nghiệp vụ; không xem chúng là phép kiểm tra chủ sở hữu dữ liệu thay cho backend.

### Bước 4 — Tích hợp API và xác minh token

Cấu hình API Gateway JWT/User Pool authorizer hoặc backend verifier. Kiểm tra signature/JWKS rotation, issuer, token type, client/audience, expiry và scopes. Test **hai người dùng khác nhau** với cùng đường dẫn tài nguyên để chứng minh không đọc nhầm dữ liệu.

### Bước 5 — Tạo Identity Pool chỉ nếu cần AWS credentials cho client

Liên kết User Pool/App Client hoặc IdP ngoài. Định nghĩa authenticated role, **guest role chỉ khi thật sự cần**, role mapping, IAM trust/permission policy, bucket policy và KMS. Kiểm tra Logins map, IdentityId và SDK credentials provider. Không thử bằng quyền AdministratorAccess.

### Bước 6 — Kiểm thử lỗi, vòng đời và quan sát

Thử token expired/revoked, JWT issuer sai, missing scope, guest role bị từ chối, IAM AccessDenied, prefix S3 của người khác, CORS, refresh tokens, key rotation, IdP outage và thời điểm triển khai role policy mới. Ghi log tối thiểu có thể truy vết nhưng không chứa tokens/credentials.

## 11. AWS CLI: kiểm kê hai loại Pool mà không tạo tài nguyên

Các lệnh chỉ **đọc cấu hình** và yêu cầu AWS identity có quyền phù hợp. Region **ap-southeast-1**, User Pool ID, App Client ID và Identity Pool ID dưới đây là placeholders. **Không** gọi API sign-in với tài khoản thật, in tokens hay cấp credentials trong ví dụ kiểm kê.

### 11.1. Xem User Pools và cấu hình đăng nhập

~~~bash
# Liệt kê User Pools hiện có trong Region được chọn.
aws cognito-idp list-user-pools \
  --region ap-southeast-1 \
  --max-results 20 \
  --query 'UserPools[].{Id:Id,Name:Name,LastModified:LastModifiedDate}' \
  --output table

# Xem một User Pool cụ thể.
aws cognito-idp describe-user-pool \
  --region ap-southeast-1 \
  --user-pool-id ap-southeast-1_EXAMPLE \
  --query 'UserPool.{Id:Id,Name:Name,Domain:Domain,MfaConfiguration:MfaConfiguration,Policies:Policies}' \
  --output json

# Xem các App Clients trong User Pool.
aws cognito-idp list-user-pool-clients \
  --region ap-southeast-1 \
  --user-pool-id ap-southeast-1_EXAMPLE \
  --max-results 20 \
  --output table

# Xem một App Client để rà soát OAuth flows/callbacks.
aws cognito-idp describe-user-pool-client \
  --region ap-southeast-1 \
  --user-pool-id ap-southeast-1_EXAMPLE \
  --client-id APP_CLIENT_ID \
  --query 'UserPoolClient.{ClientId:ClientId,Name:ClientName,CallbackURLs:CallbackURLs,LogoutURLs:LogoutURLs,AllowedOAuthFlows:AllowedOAuthFlows,AllowedOAuthScopes:AllowedOAuthScopes}' \
  --output json
~~~

**Bảo mật:** phản hồi **DescribeUserPoolClient** đầy đủ có thể chứa trường bí mật của confidential app client. Vì vậy ví dụ chỉ chọn một số field không nhạy cảm; không chuyển đầu ra đầy đủ vào issue/ticket/chat công khai. Khi cần kiểm tra app client có secret hay không, chỉ báo cáo cờ/đánh giá từ môi trường được phép, không sao chép giá trị secret.

### 11.2. Xem Identity Pools, providers và IAM roles

~~~bash
# Liệt kê Identity Pools.
aws cognito-identity list-identity-pools \
  --region ap-southeast-1 \
  --max-results 20 \
  --query 'IdentityPools[].{Id:IdentityPoolId,Name:IdentityPoolName}' \
  --output table

# Xem thông tin provider và guest access.
aws cognito-identity describe-identity-pool \
  --region ap-southeast-1 \
  --identity-pool-id ap-southeast-1:11111111-2222-3333-4444-555555555555 \
  --query '{Id:IdentityPoolId,Name:IdentityPoolName,Guest:AllowUnauthenticatedIdentities,UserPoolProviders:CognitoIdentityProviders,OpenIdProviders:OpenIdConnectProviderARNs}' \
  --output json

# Đọc IAM role ARNs và role mappings.
aws cognito-identity get-identity-pool-roles \
  --region ap-southeast-1 \
  --identity-pool-id ap-southeast-1:11111111-2222-3333-4444-555555555555 \
  --output json
~~~

Các lệnh trên giúp phát hiện Identity Pool nào đang cho guest access, liên kết User Pool/App Client nào, và roles đang được chọn. **GetIdentityPoolRoles** chỉ cho biết role assignment/mapping; để đánh giá quyền thật phải đọc **IAM trust policy, identity-based permissions, resource policies, permission boundaries/SCP** bằng quy trình kiểm toán phù hợp.

**Chú ý tên dịch vụ AWS CLI:**

- **cognito-idp**: thao tác với **User Pools và app clients**.
- **cognito-identity**: thao tác với **Identity Pools và federated identity**.

Đây là cách nhận diện nhanh khi đọc CloudTrail logs, IaC hoặc lỗi SDK. API cho **cognito-idp** không phải API để phát hành IAM temporary credentials cho end users.

## 12. Mô hình an ninh: những rủi ro quan trọng nhất

### 12.1. Threat model theo ba tài sản

| Tài sản | Rủi ro | Bảo vệ chính |
|---|---|---|
| **User session / JWT** | Token bị lộ, replay, token hết hạn, nhầm loại token | HTTPS, PKCE, CSRF state, secure storage, signature/issuer/scope/exp checks |
| **Identity Pool credentials** | Guest hoặc client nhận role quá rộng, credentials bị đánh cắp | Trust aud/amr, least-privilege IAM, TTL, scope theo identity, audit |
| **Dữ liệu nghiệp vụ** | Người hợp lệ xem object/order của người khác | Backend object-level authorization, S3 prefix/resource policies, tenant isolation |

Với SPA/mobile, không có cách nào giữ một client secret tĩnh không bị trích xuất đáng tin cậy. **Public client + PKCE** là phương án phù hợp hơn. Nếu ứng dụng sử dụng server-side session/BFF, kiểm tra cookies **HttpOnly/Secure/SameSite**, CSRF và bảo vệ refresh tokens tại backend.

### 12.2. Rủi ro token type confusion

Một backend nhận **Bearer ID token** trên route dành cho **access token** có thể bỏ qua chính sách scope. Cần kiểm tra **token_use = access** và các claims tương ứng, hoặc sử dụng authorizer đã cấu hình route scope. **Đừng** chỉ kiểm tra một chữ ký hợp lệ rồi cho mọi yêu cầu qua.

Tương tự, **Identity Pool ID token flow** phải dùng đúng **User Pool ID token**, không đổi sang access token chỉ vì hai token đều là JWT.

### 12.3. Rủi ro IAM role trust quá rộng

IAM role tin cậy **cognito-identity.amazonaws.com** mà không ràng buộc đúng **Identity Pool aud** có thể tạo cửa ngõ assume role sai phạm vi. Authenticated role cần hạn chế **amr = authenticated**; guest role cần điều kiện rõ ràng và permissions rất hẹp. Không tin rằng chỉ cần role tên **AppAuthenticatedRole** thì AWS tự biết nó chỉ dành cho người đăng nhập.

### 12.4. Phân quyền chéo tenant

Trong SaaS nhiều tenant, **User Pool group/Identity Pool role** có thể hỗ trợ phân lớp, nhưng không đủ nếu mọi tenant dùng cùng một IAM role hoặc một endpoint API. Backend phải kiểm tra **tenantId** và ownership dựa trên nguồn đáng tin cậy. Với truy cập trực tiếp S3, cần policy variables/ABAC hoặc cách tách bucket/prefix đã được kiểm chứng, không để client tự khai báo tenantId rồi tin đó là quyền.

### 12.5. MFA, quản lý account và fraud

User Pool có thể áp dụng MFA, chính sách password, account recovery, passkeys hoặc cơ chế bảo vệ nâng cao tùy tier và tính năng được hỗ trợ. Nên kích hoạt bảo vệ phù hợp với rủi ro ứng dụng, phân nhóm tài khoản quản trị và người dùng bình thường. **Identity Pool không thay MFA hoặc chính sách đăng nhập**; nó chỉ nhận bằng chứng từ nhà cung cấp danh tính đã được cấu hình.

**Định danh workforce khác khách hàng ứng dụng:** khi bài toán là nhân viên truy cập AWS accounts, AWS IAM Identity Center có thể phù hợp hơn. Không coi Cognito User Pool là giải pháp mặc định thay thế mọi hệ thống danh tính nội bộ doanh nghiệp.

## 13. Lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân khả dĩ | Bước kiểm tra |
|---|---|---|
| Đăng nhập User Pool thất bại | User chưa xác minh, MFA challenge chưa hoàn tất, mật khẩu/flow sai | User status, app client auth flows, challenge response |
| OAuth trả **invalid_client** | Sai client ID/secret, confidential client auth lỗi | Public/confidential client type, token endpoint config |
| OAuth trả **invalid_grant** | Authorization code hết hạn, dùng lại, redirect hoặc PKCE không hợp lệ | Callback, code exchange một lần, code_verifier |
| OAuth trả **invalid_scope** | Scope chưa được cấp trên app client hoặc request sai | Resource server và AllowedOAuthScopes |
| API Gateway trả **401** | JWT thiếu/sai, signature/iss/aud/exp sai | Issuer, JWKS kid, token type, app client |
| API Gateway trả **403** | Route scope/authorization không phù hợp hoặc backend từ chối | OAuth scope, IAM/API policy, object-level permission |
| Token decode được nhưng API vẫn từ chối | Decode không phải verify, wrong issuer/token_use | Verify JWT và claims theo API |
| Identity Pool báo **Token is not from a supported provider** | Logins key sai, User Pool/App Client chưa đăng ký, gửi sai token | Provider name, region, đúng ID token, client mapping |
| **InvalidIdentityPoolConfigurationException** | Không gán IAM role hoặc role trust aud/amr sai | Identity Pool roles, IAM trust principal/conditions |
| **Unauthenticated access is not supported** | Guest chưa bật nhưng app gọi Identity Pool không có Logins | Bật guest có kiểm soát hoặc yêu cầu login |
| STS **AccessDenied** khi assume role | Role trust không cho đúng identity pool/auth state, boundary/policy chặn | aud, amr, role, account, SCP và error context |
| S3 trả **AccessDenied** sau khi lấy credentials | IAM role thiếu s3 actions, prefix sai, bucket/KMS policy không cho | IdentityId, role, object ARN, bucket policy, KMS, Block Public Access |
| Browser bị **CORS** khi gọi S3 | CORS rule không cho origin/method/header, không nhất thiết IAM sai | Browser network tab, S3 CORS config, IAM riêng |
| User Pool login được nhưng AWS SDK báo credentials missing | Chưa cấu hình Identity Pool/credentials provider, refresh lỗi | SDK auth + credentials config, Identity Pool ID, Logins |
| Người dùng nhóm admin không được cấp role tương ứng | Role mapping, token claim, ambiguous resolution hoặc trust sai | ID token claims, PreferredRole, mappings |
| Chuyển tài khoản/IdP, IdentityId thay đổi | Identity mapping và linking không như dự kiến | IdP subject, GetId response, mapping backend |
| User sign-out rồi token cũ vẫn verify offline | JWT signature/exp còn hợp lệ sau revoke | Token lifetime, revocation strategy, backend session policy |

### 13.1. Quy trình chẩn đoán theo tầng

~~~mermaid
flowchart TD
    A["Người dùng không truy cập được tài nguyên"] --> B{"Lỗi xảy ra ở đâu?"}
    B -->|"Login / OAuth"| UP["User Pool: app client,<br/>MFA, PKCE, redirect, IdP"]
    B -->|"API 401 / 403"| API["JWT issuer/audience/exp/scope<br/>và backend object authorization"]
    B -->|"GetId / credentials"| IP["Identity Pool providers, Logins,<br/>roles, trust aud/amr"]
    B -->|"AWS API AccessDenied"| IAM["IdentityId + IAM permission<br/>resource policy + KMS"]
    UP --> END["Sửa đúng lớp, thử lại với<br/>hai user/tenant, ghi bằng chứng"]
    API --> END
    IP --> END
    IAM --> END
~~~

**Không nới role sang AdministratorAccess chỉ để kiểm tra lỗi S3 403.** Trước tiên xác định request đang dùng JWT, AWS temporary credentials hay một session của backend; tìm policy thực sự chặn; chỉ cấp lại quyền tối thiểu cần thiết.

### 13.2. Phân biệt 401, 403 và CORS

- **401 Unauthorized** thường biểu thị thiếu hoặc không chấp nhận được bằng chứng xác thực ở API.
- **403 Forbidden** thường là đã nhận request nhưng không có quyền, hoặc deny từ WAF/resource policy/authorizer.
- **CORS error** là cơ chế trình duyệt chặn truy cập response từ origin khác; không đủ kết luận IAM hay User Pool sai.

Cần xem **HTTP status**, response body, CloudTrail/CloudWatch logs, origin của request, preflight OPTIONS và quyền thực tế. Một browser có thể hiển thị CORS error trong khi service backend trả lỗi auth; kiểm tra network trace để phân biệt.

## 14. Vận hành, monitoring và khả năng phục hồi

### 14.1. Quan sát các lớp quan trọng

| Lớp | Theo dõi gì? | Nguồn gợi ý |
|---|---|---|
| **User Pool sign-in** | Authentication failures, MFA challenges, account lockout, token requests | Cognito/CloudWatch metrics, IdP logs theo cấu hình |
| **API authorization** | 401/403, JWT verifier failures, invalid scopes | API Gateway access logs, Lambda/Java application logs |
| **Identity Pool federation** | Lỗi GetId/GetCredentials, guest usage, role mapping thất bại | CloudTrail/AWS service metrics và ứng dụng telemetry phù hợp |
| **STS/IAM** | AccessDenied, assume role failures, policy changes | CloudTrail, IAM Access Analyzer và kiểm toán IAM |
| **S3/DynamoDB** | 403, access patterns, data transfer, sai prefix | Service logs/metrics, CloudTrail data events khi được bật |
| **Identity provider ngoài** | IdP outage, certificate/metadata rotation, response latency | IdP health và application auth traces |

**CloudTrail không tự ghi mọi lần người dùng đăng nhập qua giao diện như một application access log đầy đủ**. Cần xác định chính xác dữ liệu giám sát do từng lớp xuất ra; ứng dụng phải tự ghi các sự kiện nghiệp vụ thích hợp và không đưa tokens, passwords, secret hoặc PII quá mức vào log.

### 14.2. Vì sao phải chuẩn bị cho lỗi đăng nhập?

Không giả định một Cognito user pool có cơ chế failover tự động sang user pool khác ở Region khác. User Pool và Identity Pool có **Region và IDs cụ thể**, JWT **issuer** gắn với User Pool. Nếu hệ thống có yêu cầu **DR liên Region**, cần kế hoạch riêng cho tài khoản, identity federation, app clients, domain/callbacks, dữ liệu hồ sơ, mật khẩu/khôi phục tài khoản, secrets, DNS và backend.

**Không thể đơn giản đổi DNS sang User Pool khác rồi mặc định JWT cũ có issuer/audience được tin cậy.** Phải có kế hoạch migration/federation, token validation và trải nghiệm người dùng khi chuyển đổi.

### 14.3. Token expiry, revocation và IdP outage

Khi access token hết hạn, ứng dụng có thể refresh nếu còn refresh token hợp lệ. Khi user bị khóa hoặc token bị revoke, cần thiết kế cách API từ chối theo độ nhạy dữ liệu. JWT verification offline không nhất thiết nhận biết revoke ngay lập tức. Với IdP ngoài bị gián đoạn, đăng nhập mới có thể thất bại dù một số sessions/tokens còn hạn; lựa chọn fallback phải tuân thủ chính sách an ninh và có thể yêu cầu xác thực lại sau sự cố.

## 15. Chi phí và lựa chọn sản phẩm

Theo mô hình giá AWS hiện hành, **Cognito User Pools** có các tier như **Lite, Essentials và Plus**, với phí có thể dựa trên **monthly active users (MAU)**, loại federation và tính năng. **Machine-to-machine token requests** hoặc các khả năng nâng cao có thể có mô hình phí riêng. Cần kiểm tra bảng giá mới nhất theo Region/tier thay vì gán một đơn giá cố định cho mọi User Pool.

**Identity Pools** hiện không tính phí riêng cho việc **xác thực người dùng và tạo unique identifiers** theo trang giá AWS. Điều này **không có nghĩa ứng dụng dùng Identity Pool hoàn toàn miễn phí**: S3/DynamoDB requests, data transfer, API Gateway, WAF, CloudWatch, SMS/email MFA, Lambda triggers và các dịch vụ liên quan vẫn có phí theo cơ chế của chúng.

| Hạng mục | Cần đưa vào dự toán |
|---|---|
| **User Pool tier** | MAU, kiểu đăng nhập trực tiếp/social/SAML/OIDC, tier Lite/Essentials/Plus |
| **OAuth/M2M** | Token requests đặc biệt hoặc flow machine-to-machine khi áp dụng |
| **MFA/notifications** | SMS, email, delivery service và chống gian lận |
| **Lambda triggers** | Invocations/duration của custom authentication và pre-token generation |
| **Identity Pool + AWS resources** | IAM credentials có giới hạn nhưng AWS API được gọi vẫn có chi phí |
| **Observability** | CloudWatch logs/metrics, CloudTrail data events, WAF, tracing |
| **DR và vận hành** | Đa Region nếu cần, account migration, auth incident, support |

**Không tạo Identity Pool chỉ vì nghĩ phải có để giảm chi phí auth.** Nó giải quyết nhu cầu **AWS credential federation**, không thay đổi bản chất chi phí quản lý đăng nhập của User Pool. Nếu mục tiêu là tải/đọc một vài object, so sánh Identity Pool direct credentials với **presigned URLs** do backend phát hành trước khi chọn.

## 16. Bài tập tình huống

### Tình huống A — Website đặt hàng có REST API

Ứng dụng Java Spring Boot chạy sau API Gateway và có cơ sở dữ liệu RDS. Khách hàng đăng nhập bằng email/MFA, sau đó cần xem đơn hàng của mình. Frontend không trực tiếp gọi S3/DynamoDB.

**Câu hỏi:** chọn User Pool, Identity Pool hay cả hai?

**Gợi ý:** **User Pool** thường đủ để đăng nhập và phát hành access JWT. API Gateway/backend kiểm tra token, scope, tenant/owner; Spring Boot truy cập RDS bằng cấu hình backend được bảo vệ. Identity Pool không cần thiết chỉ để kiểm tra JWT.

### Tình huống B — Ứng dụng ảnh tải file cá nhân từ S3

Ứng dụng mobile có đăng nhập User Pool và muốn đọc/ghi ảnh theo mỗi người dùng trực tiếp bằng AWS SDK.

**Câu hỏi:** Identity Pool cung cấp giá trị gì, quyền phải ràng buộc ra sao?

**Gợi ý:** dùng User Pool **ID token** đưa vào Identity Pool, nhận **IdentityId** và temporary credentials của authenticated IAM role. Policy S3 chỉ cho phép prefix tương ứng **Identity Pool identity ID**, cộng với bucket/KMS policy; giới hạn upload, object validation và SDK credential refresh.

### Tình huống C — Ứng dụng chỉ đăng nhập Google

Nhóm đã có đăng nhập Google/OIDC và không cần User Pool quản lý user profiles, nhưng cần AWS credentials tạm thời để tải các file được kiểm soát.

**Câu hỏi:** có bắt buộc tạo User Pool không?

**Gợi ý:** không. Có thể liên kết Identity Pool trực tiếp với IdP phù hợp và định nghĩa IAM roles. Tuy nhiên, nếu muốn một issuer OIDC chung, mapping attributes, account management hoặc các flows do Cognito quản lý, User Pool là một ứng viên riêng.

### Tình huống D — Guest credentials bị lợi dụng

Identity Pool bật **AllowUnauthenticatedIdentities** để đọc một ảnh public, nhưng guest IAM role lại có **s3:* trên toàn bucket**.

**Câu hỏi:** vì sao đây là rủi ro cao?

**Gợi ý:** bất kỳ khách chưa đăng nhập nào cũng có thể nhận temporary credentials với quyền guest. Tắt guest nếu không cần; hoặc chỉ cấp **s3:GetObject** cho đúng asset, cân nhắc CloudFront public làm thay thế. Kiểm tra role trust aud/amr và giám sát lưu lượng.

### Tình huống E — JWT hợp lệ nhưng bị từ chối ở API

Client gửi ID token thay vì access token khi gọi **GET /orders/123**, trong khi API Gateway route yêu cầu scope **orders/read**.

**Câu hỏi:** tại sao JWT signature hợp lệ không đồng nghĩa API phải chấp nhận?

**Gợi ý:** ID token mô tả danh tính, còn access token có OAuth scopes. Kiểm tra **token_use**, route scopes, issuer/client/audience và dùng access token đúng; backend vẫn cần xác nhận order 123 thuộc người gọi.

### Tình huống F — Identity Pool báo InvalidIdentityPoolConfigurationException

Login thành công, ứng dụng nhận User Pool ID token và GetId trả IdentityId, nhưng **GetCredentialsForIdentity** không cấp credentials.

**Câu hỏi:** kiểm tra những gì?

**Gợi ý:** Identity Pool authenticated role assignment, role mapping, role trust principal **cognito-identity.amazonaws.com**, condition **aud** phải là Identity Pool ID và **amr=authenticated**, tài khoản/role và IAM restrictions. Không gắn AdministratorAccess để che lỗi trust.

### Tình huống G — Kỹ sư nhầm sub của hai Pool

Backend tạo object theo **User Pool sub**, còn IAM policy của authenticated role lại giới hạn prefix theo **cognito-identity.amazonaws.com:sub**. Người dùng nhận AccessDenied.

**Câu hỏi:** phải sửa cách lập đường dẫn hay quyền?

**Gợi ý:** hai **sub/IdentityId** không cùng giá trị. Quyết định khóa định danh hệ thống, tạo mapping đáng tin cậy và cập nhật object prefix/policy thích hợp. Không cho client chọn tùy ý một prefix khác để bypass quyền.

## 17. Checklist triển khai production

- [ ] Đã ghi rõ nhu cầu **authentication**, **API authorization** và **AWS IAM authorization**.
- [ ] Chỉ tạo **User Pool** khi cần chức năng login/user directory/OIDC issuer; chỉ tạo **Identity Pool** khi cần temporary AWS credentials cho client.
- [ ] Đã xác định User Pool, App Client, Identity Pool và IdentityId là bốn định danh khác nhau.
- [ ] Public app dùng Authorization Code + **PKCE**, **state** và redirect URI hợp lệ; không nhúng client secret.
- [ ] Đã bật MFA/account recovery và chính sách bảo vệ đăng nhập theo rủi ro.
- [ ] API verify signature, **iss**, **exp**, **token_use**, client/audience và **scope**.
- [ ] Backend kiểm tra quyền đến **từng object/order/tenant**, không chỉ nhóm và JWT hợp lệ.
- [ ] Khi User Pool liên kết Identity Pool, dùng **ID token** đúng Logins provider key và App Client.
- [ ] IAM role trust có **aud = Identity Pool ID**, **amr** phù hợp, principal và account đúng.
- [ ] Authenticated/guest IAM policies là **least privilege**; guest access tắt nếu không cần.
- [ ] AWS temporary credentials được SDK quản lý/refresh; không log hoặc lưu như khóa lâu dài.
- [ ] Nếu truy cập S3 trực tiếp, đã kiểm tra prefix theo IdentityId, bucket policy, KMS, CORS, upload security.
- [ ] Đã thiết kế token storage, expiration, refresh/revocation và JWKS rotation.
- [ ] Đã có cảnh báo auth errors, API 401/403, STS/IAM AccessDenied và kiểm toán thay đổi roles/policies.
- [ ] Đã kiểm thử hai user/tenant, guest, expired token, wrong issuer, missing scope, sai role mapping.
- [ ] Đã cân nhắc lỗi IdP/Region, DR, profile migration và token issuer khi phục hồi.
- [ ] Đã dự toán User Pool tier/MAU, SMS, triggers, CloudWatch, API Gateway/S3 và các phí liên quan.

## 18. Ghi nhớ

**Cognito User Pool** trả lời bài toán **đăng ký, đăng nhập, liên kết identity providers và phát hành ID/access/refresh tokens**. Một web/mobile app gọi API của mình qua **access token** thường **không cần Identity Pool**. **Cognito Identity Pool** trả lời bài toán **trao danh tính đã xác thực hoặc guest cho IAM roles và AWS temporary credentials**, để client dùng AWS SDK truy cập tài nguyên theo quyền giới hạn.

Khi kết hợp cả hai, luồng chuẩn là **User Pool đăng nhập → ID token đưa vào Identity Pool → GetId + GetCredentialsForIdentity → IAM role/STS temporary credentials → signed AWS request**. Đừng nhầm User Pool **sub** với Identity Pool **IdentityId**, đừng nhầm **access JWT** với **AWS AccessKeyId**, và đừng để JWT hợp lệ trở thành lý do bỏ qua quyền ở mức order/file/tenant.

### Tài liệu AWS chính thức để tham khảo

- [What is Amazon Cognito?](https://docs.aws.amazon.com/cognito/latest/developerguide/what-is-amazon-cognito.html) — bảng so sánh User Pools và Identity Pools.
- [Authenticating users with Amazon Cognito user pools](https://docs.aws.amazon.com/cognito/latest/developerguide/cognito-user-pools.html) — quản lý tài khoản, liên kết IdPs, đăng nhập.
- [Understanding user pool JSON web tokens](https://docs.aws.amazon.com/cognito/latest/developerguide/amazon-cognito-user-pools-using-tokens-with-identity-providers.html) — ID/access/refresh tokens.
- [Verifying JSON web tokens](https://docs.aws.amazon.com/cognito/latest/developerguide/amazon-cognito-user-pools-using-tokens-verifying-a-jwt.html) — signature, issuer, scopes và JWKS.
- [Using PKCE in authorization code grants](https://docs.aws.amazon.com/cognito/latest/developerguide/using-pkce-in-authorization-code.html) — bảo vệ OAuth public clients.
- [Application-specific settings with app clients](https://docs.aws.amazon.com/cognito/latest/developerguide/user-pool-settings-client-apps.html) — public/confidential app clients.
- [Amazon Cognito identity pools](https://docs.aws.amazon.com/cognito/latest/developerguide/cognito-identity.html) — identity federation và AWS credentials.
- [Identity pools authentication flow](https://docs.aws.amazon.com/cognito/latest/developerguide/authentication-flow.html) — GetId, GetCredentialsForIdentity, enhanced/basic.
- [Access AWS resources with an identity pool after sign-in](https://docs.aws.amazon.com/cognito/latest/developerguide/amazon-cognito-integrating-user-pools-with-identity-pools.html) — luồng kết hợp hai Pool.
- [IAM roles for identity pools](https://docs.aws.amazon.com/cognito/latest/developerguide/iam-roles.html) — trust aud/amr, IAM policy variables.
- [Role-based access control in identity pools](https://docs.aws.amazon.com/cognito/latest/developerguide/role-based-access-control.html) — role mapping theo claims.
- [Identity pool security best practices](https://docs.aws.amazon.com/cognito/latest/developerguide/identity-pools-security-best-practices.html) — least privilege và guest access.
- [Troubleshooting Amazon Cognito](https://docs.aws.amazon.com/cognito/latest/developerguide/troubleshooting.html) — token, IAM role và IdP errors.
- [Amazon Cognito pricing](https://aws.amazon.com/cognito/pricing/) và [AWS Pricing Calculator](https://calculator.aws/) — phí hiện hành theo tier và dịch vụ liên quan.


