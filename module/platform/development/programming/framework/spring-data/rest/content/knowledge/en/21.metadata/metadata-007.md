# Internationalizing Descriptions with rest-messages.properties in Spring Data REST

## Objectives

Spring Data REST provides metadata describing repositories, resources, and domain properties. You can write these descriptions in a message bundle so the API returns content matching the client's language.

This mechanism is useful when the same API serves multiple user groups, such as Vietnamese and English interfaces. You can localize the metadata descriptions without changing endpoint names, property names, or business data.

After this lesson, you will be able to:

- Create a message bundle for Spring Data REST resource descriptions.
- Declare message keys by resource and property.
- Separate content by locale using language suffixes.
- Send requests with `Accept-Language` and inspect the returned metadata.

## 1. What Are Resource Descriptions in Spring Data REST?

When exporting repositories, Spring Data REST exposes resources and metadata so clients can discover the API. Descriptions help clients understand the meaning of a resource or property without reading the server source code.

For example, a user management application has a repository published at the collection resource **/people**, with domain type **Person** containing properties **firstName** and **lastName**.

Descriptions can provide information such as:

- Resource **people** contains a list of users.
- Resource **person** represents a single user.
- Property **firstName** stores the first name.
- Property **lastName** stores the last name.

Spring Data REST can include these descriptions in the API's metadata/profile, such as ALPS. Clients can read the metadata to understand the resources and properties exposed.

Distinguish metadata descriptions from entity data. Internationalizing the description of **firstName** does not alter the actual value of the **firstName** field in JSON responses.

## 2. Creating rest-messages.properties

Create the file **rest-messages.properties** in the application's resources directory:

~~~text
src/
└── main/
    └── resources/
        └── rest-messages.properties
~~~

Example default content in English:

~~~properties
rest.description.people=Collection of people available in the system.
rest.description.person=An individual person resource.
rest.description.person.firstName=The first name of the person.
rest.description.person.lastName=The last name of the person.
~~~

Keys have the prefix **rest.description.**. The following part identifies the resource or property to describe.

In the example:

- **rest.description.people** describes the collection resource with relation **people**.
- **rest.description.person** describes the resource for domain type **Person**.
- **rest.description.person.firstName** describes the **firstName** property.
- **rest.description.person.lastName** describes the **lastName** property.

Relation names and domain type names depend on how the application exports repositories. If you customize a repository path, relation, or property name, use the exact name Spring Data REST uses when resolving descriptions. Do not infer keys from URLs if the relation has been customized.

## 3. Creating Message Bundles per Language

Java `ResourceBundle` supports files with locale suffixes. You can keep a default bundle and create separate files for each language.

Example structure:

~~~text
src/main/resources/
├── rest-messages.properties
├── rest-messages_en.properties
└── rest-messages_vi.properties
~~~

File **rest-messages_vi.properties** contains Vietnamese descriptions:

~~~properties
rest.description.people=Danh sách người dùng có trong hệ thống.
rest.description.person=Thông tin tài nguyên của một người dùng.
rest.description.person.firstName=Tên của người dùng.
rest.description.person.lastName=Họ của người dùng.
~~~

File **rest-messages_en.properties** can contain English content:

~~~properties
rest.description.people=Collection of people available in the system.
rest.description.person=An individual person resource.
rest.description.person.firstName=The first name of the person.
rest.description.person.lastName=The last name of the person.
~~~

The file without a locale suffix, **rest-messages.properties**, serves as the default bundle. When a locale lacks a corresponding message, the `ResourceBundle` mechanism can fall back to the default bundle.

You do not need to recreate the key structure for each language. Keep the keys identical and translate only the values. As a result, clients receive the same API metadata structure even as the description text varies by locale.

## 4. Registering the Basename in Spring Boot

The application needs a `MessageSource` configured with the basename **rest-messages** so messages in the bundle are resolved.

You can declare this in **application.yml**:

~~~yaml
spring:
  messages:
    basename: rest-messages
    encoding: UTF-8
~~~

If the application already uses other bundles, keep them in the basename list instead of overwriting existing configuration. For example:

~~~yaml
spring:
  messages:
    basename: messages,rest-messages
    encoding: UTF-8
~~~

With this configuration, Spring Boot registers bundles according to the declared basenames. Spring Data REST uses `MessageSource` to resolve the corresponding metadata descriptions.

If the application defines a custom **MessageSource** bean, make sure that bean also includes basename **rest-messages** and supports the required locales. Avoid creating multiple independent `MessageSource` instances where the bundle is registered in one place while Spring Data REST uses a different message source.

Save properties files in UTF-8 so accented or non-ASCII text is read accurately. With UTF-8 encoding configured, diacritics are preserved when messages are resolved.

## 5. Clients Requesting a Language via Accept-Language

Clients can send the HTTP header **Accept-Language** to indicate their desired locale.

Example requesting Vietnamese metadata:

~~~http
GET /profile
Accept: application/alps+json
Accept-Language: vi
~~~

Example requesting English metadata:

~~~http
GET /profile
Accept: application/alps+json
Accept-Language: en
~~~

If the API provides a `profile` link in the response, the client should use the profile URL returned by the server. The **/profile** path above is an example under a common configuration; base paths and metadata publishing may vary by application.

Spring MVC can typically determine the locale from the **Accept-Language** header. If the application customizes locale resolution, check that configuration to ensure the request locale is propagated to `MessageSource`.

When the locale is **vi**, message keys with translations in **rest-messages_vi.properties** resolve to Vietnamese. When the locale is **en**, the English bundle is used if present.

## 6. Verifying Localized Descriptions

After creating the bundles and configuring `MessageSource`, verify with the following steps:

1. Start the application and confirm the repository resources are exported.
2. Send a request to the profile or metadata endpoint with **Accept-Language: vi**.
3. Locate descriptors whose descriptions match the declared resources and properties.
4. Resend the request with **Accept-Language: en**.
5. Compare the description values to confirm the locale took effect.

For example, the same descriptor can have a Vietnamese description in the first request and an English description in the second. Keys, relations, and metadata structure remain unchanged.

If the text does not change by locale, check:

- Whether file names follow the **rest-messages_vi.properties** or **rest-messages_en.properties** convention.
- Whether basename **rest-messages** is registered in `MessageSource`.
- Whether keys match the exported resource relations, domain types, and property names.
- Whether the **Accept-Language** header is sent to the right endpoint.
- Whether the application has a custom `LocaleResolver` or `MessageSource` altering locale resolution.
- Whether the bundle was packaged onto the classpath after building.

## 7. Scope of rest-messages.properties

**rest-messages.properties** serves metadata descriptions that Spring Data REST looks up through `MessageSource`. Do not treat it as an automatic translation mechanism for all API content.

| Content | Appropriate Handling |
|---|---|
| Spring Data REST repository/resource/property descriptions | Use description keys in the `rest-messages` bundle |
| Entity data values, such as a user's name | Store and return data according to business logic; do not translate via resource descriptions |
| Validation messages | Use Spring's message bundles and validation mechanism |
| Messages in custom controllers | Use `MessageSource` or the application's i18n mechanism |
| URLs, repository paths, relation names | API configuration; must not be changed merely because descriptions are translated |

Key points to keep in mind:

- **Keep keys stable:** all locales must use the same keys so clients receive a consistent metadata structure.
- **Translate values, not keys:** do not change **rest.description.person.firstName** into a Vietnamese key.
- **Provide a default bundle:** supply default messages to avoid missing descriptions when a locale is unsupported.
- **Verify fallbacks:** if a key is missing in a locale-specific bundle, inspect the fallback output and add missing translations.
- **Do not confuse locale with time zone:** `Accept-Language` selects language, not time zone or business data formatting.
- **Update client documentation:** if clients render metadata descriptions, define a consistent way to send the locale across requests.

## Key Takeaways

To internationalize metadata descriptions in Spring Data REST, create **rest-messages.properties**, declare **rest.description.*** keys for resources and properties, and add locale-specific bundles such as **rest-messages_vi.properties** and **rest-messages_en.properties**. Register basename **rest-messages** in `MessageSource` and send **Accept-Language** from the client. This localizes metadata descriptions while keeping keys and API structure unchanged.
