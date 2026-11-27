# Calling the Azure Resource Manager REST API

Azure Resource Manager (ARM) is the unified management layer of Azure. Whenever you create a resource group, deploy a virtual machine, change a network configuration, or list resources in a subscription, tools such as the Azure Portal, Azure CLI, Azure PowerShell, SDKs, and deployment templates all send requests to this management layer. Beyond those tools, you can call the **Azure Resource Manager REST API** directly over HTTP to automate workflows, integrate Azure with external systems, or understand exactly how an administrative operation takes place.

This lesson guides you through authenticating with Microsoft Entra ID, constructing URLs and requests, performing common operations, tracking asynchronous operations, and handling errors when calling the ARM REST API. The content is scoped to managing subscriptions, resource groups, identities, and services within the Microsoft Azure ecosystem.

## Learning Objectives

After this lesson, you will be able to:

- Explain the role of ARM and distinguish the management plane from the data plane.
- Obtain an appropriate access token from Microsoft Entra ID and understand the role of Azure RBAC.
- Construct requests with resource IDs, HTTP methods, and API versions.
- Use the REST API to read, create, update, and delete Azure resources.
- Track long-running operations, handle pagination, throttling, and HTTP errors.
- Protect credentials and apply least privilege when automating.

## 1. What Is the Azure Resource Manager REST API?

ARM is Azure's control plane: the layer that receives and orchestrates resource management operations. ARM provides a unified management interface across many resource types, such as Virtual Machines, Virtual Networks, Storage Accounts, Azure SQL, and resource groups.

The REST API lets clients send HTTP requests to Azure's management endpoint. A request typically specifies:

- **Endpoint**: the ARM server, usually `https://management.azure.com` for the Azure public cloud.
- **Resource ID**: the path identifying the subscription, resource group, or resource to operate on.
- **API version**: the API contract version of the resource provider.
- **HTTP method**: the action to perform, such as GET, PUT, PATCH, DELETE, or POST.
- **Headers and body**: authentication details, content format, and payload sent if required by the operation.

For example, when the Azure Portal creates a resource group, it also sends the corresponding management request to ARM. When you call the REST API directly, you construct the request yourself instead of having the Portal or CLI build it for you.

### Management plane and data plane

These two endpoint types serve different purposes:

| Type | Purpose | Example |
|---|---|---|
| **Management plane** | Create, configure, list, or delete Azure resources. | Creating a Storage Account, changing VM configuration, creating a resource group via `management.azure.com`. |
| **Data plane** | Read or write the data that the service stores or processes. | Reading a blob from `https://<storage-account>.blob.core.windows.net`, querying data in a database, or sending a message to a queue. |

For example, the ARM REST API can create a Storage Account and configure redundancy. To upload a blob inside that account, the application calls the Blob Storage data-plane API. Both operations may use the same Microsoft Entra ID identity, but they require the token audience, RBAC permissions, and endpoint appropriate for their respective service.

## 2. Structure of a REST Request

A resource management request generally takes the form:

```http
<METHOD> https://management.azure.com/<resource-id>?api-version=<api-version> HTTP/1.1
Authorization: Bearer <access-token>
Content-Type: application/json
Accept: application/json

<JSON body if required by method>
```

`api-version` is a critical parameter. ARM needs to know which API contract version the client intends to use; never omit this parameter or guess a version. Each resource provider has its own API release schedule. Choose a version published in the official documentation for that resource type, prefer stable versions for production environments, and evaluate carefully if a preview version must be used.

Several commonly used HTTP methods:

| Method | Common meaning in ARM | Example |
|---|---|---|
| `GET` | Read a resource or list resources. | Viewing resource group details or a list of VMs. |
| `PUT` | Create or replace a resource configuration at a resource ID. | Creating a resource group or creating a Storage Account. |
| `PATCH` | Partially update properties if supported by the resource's API. | Modifying certain tags or configurations. |
| `DELETE` | Request deletion of a resource. | Deleting a resource group or VM. |
| `POST` | Execute an action or operation provided by a resource provider. | Starting, stopping, or deallocating a VM via an action endpoint. |

The exact semantics of the method and body depend on the endpoint. Not every resource supports PATCH, and POST can trigger an action with real side effects. Always check the operation's documentation before calling it.

### Resource ID

The Resource ID identifies the logical location of a resource in Azure. Common formats:

```text
/subscriptions/{subscriptionId}
/subscriptions/{subscriptionId}/resourceGroups/{resourceGroupName}
/subscriptions/{subscriptionId}/resourceGroups/{resourceGroupName}/providers/{resourceProviderNamespace}/{resourceType}/{resourceName}
```

Example resource ID of a virtual machine:

```text
/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-app/providers/Microsoft.Compute/virtualMachines/vm-api
```

Where:

- `subscriptionId` identifies the subscription containing the resource.
- `resourceGroups/rg-app` identifies the resource group.
- `Microsoft.Compute` is the resource provider's namespace.
- `virtualMachines/vm-api` identifies the resource type and VM name.

The Resource ID is typically used as the path segment after the ARM hostname. For child resources, the path can include additional type/name pairs, so take the exact ID from API responses or documentation instead of shortening it yourself.

## 3. Authenticating with Microsoft Entra ID

ARM does not accept a username/password embedded directly in the request. Clients must obtain an **access token** issued by Microsoft Entra ID and send that token in the header:

```http
Authorization: Bearer <access-token>
```

The token must be scoped for Azure Resource Manager. For the Azure public cloud, the resource audience is typically `https://management.azure.com/`. A token acquired for Microsoft Graph or Blob Storage cannot be substituted arbitrarily for an ARM token.

### Acquiring a token with Azure CLI

To practice on a personal machine, sign in with Azure CLI:

```bash
az login
az account list --output table
az account set --subscription "<subscription-id-or-name>"
```

Then retrieve the current subscription ID and an access token for ARM:

```bash
SUBSCRIPTION_ID=$(az account show --query id --output tsv)
TOKEN=$(az account get-access-token \
  --resource https://management.azure.com/ \
  --query accessToken \
  --output tsv)
```

The commands above use the learner's Azure CLI sign-in session. Tokens expire; if a request returns an expired token error, fetch a fresh token. Never write tokens into source code, commit them to Git, send them over chat, or store them in logs.

### User identities and application identities

In automation environments, you should not rely on an engineer's personal account. You can use:

- **Service principal**: an application identity in Microsoft Entra ID, commonly used by workloads running outside Azure or in pipelines. Prefer certificates or workload federation where appropriate; if using a client secret, store it in a secret store and rotate it per policy.
- **Managed identity**: an Azure-managed identity for supported resources, such as VMs, App Service, or Azure Functions. The application can request tokens without storing a client secret itself.
- **Workload identity federation**: allows workloads on supported platforms to exchange trusted tokens with Microsoft Entra ID without storing long-lived secrets.

For any identity type, two conditions must be met: the identity must be able to obtain a valid token for ARM, and it must have permission to execute the operation at the exact resource scope.

## 4. Azure RBAC Determines What the Request Can Do

An access token identifies the caller and related authentication claims; Azure Role-Based Access Control (Azure RBAC) determines which actions that identity is permitted to perform at which scope. Having a valid token does not guarantee a request will be accepted.

Permissions can be assigned at multiple scopes:

1. Management group.
2. Subscription.
3. Resource group.
4. Specific resource.

Permissions inherit from parent scopes down to child scopes under the Azure RBAC model. For example, an identity with an appropriate role at a resource group level can manage resources in that resource group without needing permissions across the entire subscription.

When designing integrations, choose a role with the minimum necessary set of actions. `Reader` typically fits read-only management metadata needs; create, update, or delete operations require roles with corresponding permissions. `Contributor` has a broad scope and should not be granted merely to test a single request. If custom permissions are needed, you can build a custom role tailored to the required operations and also check conditions such as Azure Policy, deny assignments, or resource locks.

Common response status codes:

- `401 Unauthorized`: token is missing, has the wrong audience, is expired, or is invalid.
- `403 Forbidden`: identity is authenticated but lacks appropriate permissions, or is blocked by a policy/condition at the relevant scope.
- `404 Not Found`: resource ID, resource name, subscription, or endpoint is incorrect; also verify whether the resource exists in the scope being called.

## 5. Calling the API to Read and Create a Resource Group

The following examples use Bash, Azure CLI, and `curl`. You need Azure CLI, `curl`, appropriate permissions on the subscription, and a successful sign-in. Replace resource group names or regions according to your practice environment.

### Listing resource groups

After setting `SUBSCRIPTION_ID` and `TOKEN` as shown previously, call:

```bash
curl --request GET \
  --url "https://management.azure.com/subscriptions/${SUBSCRIPTION_ID}/resourcegroups?api-version=2021-04-01" \
  --header "Authorization: Bearer ${TOKEN}" \
  --header "Accept: application/json"
```

This request invokes the operation to list resource groups in the subscription. A successful response typically returns HTTP `200` and JSON containing a `value` property, which is the list of resource groups. If the list is long, the response may contain `nextLink`; see the pagination section below to retrieve all results.

### Creating a resource group

Creating a resource group is a `PUT` operation targeting the resource group's resource ID:

```bash
curl --request PUT \
  --url "https://management.azure.com/subscriptions/${SUBSCRIPTION_ID}/resourcegroups/rg-rest-demo?api-version=2021-04-01" \
  --header "Authorization: Bearer ${TOKEN}" \
  --header "Content-Type: application/json" \
  --data '{
    "location": "southeastasia",
    "tags": {
      "environment": "learning",
      "managedBy": "rest-api"
    }
  }'
```

The JSON body specifies the region and tags. Replace `southeastasia` with a region meeting your requirements. If the request succeeds, the response returns metadata for the newly created or updated resource group. Check `id`, `name`, `location`, and `tags` in the result.

### Reading a resource group by name

```bash
curl --request GET \
  --url "https://management.azure.com/subscriptions/${SUBSCRIPTION_ID}/resourcegroups/rg-rest-demo?api-version=2021-04-01" \
  --header "Authorization: Bearer ${TOKEN}" \
  --header "Accept: application/json"
```

This example illustrates calling the API by resource ID. In a real environment, select an API version supported by the corresponding operation's documentation. The API version for Resource Groups is not necessarily the same as the API version for Virtual Machines or Storage.

## 6. Reading or Operating on Resource Provider Resources

Resource types are managed by resource providers. For example, VMs belong to the `Microsoft.Compute` namespace, virtual networks belong to `Microsoft.Network`, and storage accounts belong to `Microsoft.Storage`.

A request to read a VM looks like:

```bash
curl --request GET \
  --url "https://management.azure.com/subscriptions/${SUBSCRIPTION_ID}/resourceGroups/rg-app/providers/Microsoft.Compute/virtualMachines/vm-api?api-version=2024-03-01" \
  --header "Authorization: Bearer ${TOKEN}" \
  --header "Accept: application/json"
```

In this example, API version `2024-03-01` illustrates a `Microsoft.Compute` version for VM operations. Before using it, verify the supported version for the operation and resource type at deployment time. Do not use a single universal API version across all resource providers.

To create or update a resource, typically send a `PUT` to the resource's resource ID with a schema-compliant body. To modify partial properties, use `PATCH` if supported by the operation. To invoke actions such as starting a VM, resource providers typically publish an action endpoint using `POST`, for example a path like:

```text
POST /subscriptions/{subscriptionId}/resourceGroups/{resourceGroupName}/providers/Microsoft.Compute/virtualMachines/{vmName}/start?api-version={api-version}
```

This illustrative path does not replace the operation documentation: the API version, body, required permissions, and asynchronous behavior must be confirmed against the Compute API version in use. Some actions take no body, yet still require the authentication header and appropriate permissions.

## 7. Pagination When Reading Lists

A list operation may return a subset of results instead of the complete list. If the response JSON contains a `nextLink` field, the client must call that URL to retrieve the next page, continuing until `nextLink` is no longer present.

```json
{
  "value": [
    { "name": "rg-app", "location": "southeastasia" }
  ],
  "nextLink": "https://management.azure.com/..."
}
```

`nextLink` typically contains continuation query parameters. Use the URL returned by the server instead of crafting pagination tokens or incrementing offsets manually. When calling the next URL, continue sending the access token in the header. If using an HTTP library, loop until `nextLink` is absent; ignoring this field can cause reports or sync jobs to process only a subset of resources.

## 8. Asynchronous Operations and Polling

Some management operations take time, such as creating a VM, updating infrastructure configurations, or deleting large resources. ARM may return `202 Accepted` to indicate the request was accepted and the operation is still running. A `202` status does not mean the resource is ready.

The response may include one or both headers:

- `Azure-AsyncOperation`: URL used to check operation status.
- `Location`: URL related to the operation or final result, depending on the API.
- `Retry-After`: duration the client should wait before the next status check.

General workflow:

1. Send the management request and read the HTTP status along with response headers.
2. If the operation finishes immediately, process the response per the API contract.
3. If `202 Accepted` is received, save the returned polling URL and the `Retry-After` wait interval if present.
4. Call the status URL with an appropriate token, wait as instructed by the server, and repeat while the status is still running.
5. Report success only when the final status is `Succeeded` or the API confirms the resource has reached the desired state. If the status is `Failed` or `Canceled`, inspect the error details and handle appropriately.

An example response from a status endpoint may look like:

```json
{
  "status": "InProgress"
}
```

Exact status values and returned headers depend on the operation. Clients must handle cases without `Azure-AsyncOperation`, cases with `Location`, or cases where the API returns a completed result immediately. Avoid tight polling loops; honor `Retry-After` to reduce load and avoid throttling.

## 9. Handling Errors, Throttling, and Concurrent Updates

When calling the REST API, inspect both the HTTP status code and the returned JSON body. ARM commonly provides error information in a structure containing `error.code`, `error.message`, and sometimes `error.details` or `target`.

| HTTP status | Common meaning | How to handle |
|---|---|---|
| `400 Bad Request` | Invalid body, parameters, or configuration. | Check schema, API version, enum values, and required fields. |
| `401 Unauthorized` | Invalid, expired, or wrong-audience token. | Acquire a fresh token for ARM and verify the active identity. |
| `403 Forbidden` | Missing permissions or blocked by policy. | Check role assignments, scope, Azure Policy, and deny assignments. |
| `404 Not Found` | Resource or operation not found. | Verify subscription, resource ID, name, and API endpoint. |
| `409 Conflict` | Current state conflicts with the requested operation. | Read detailed error code, check running operations, and inspect resource state. |
| `429 Too Many Requests` | Requests exceeded limits or were throttled. | Honor `Retry-After`, slow down request rate, and use exponential backoff with jitter when appropriate. |
| `5xx` | Transient service or infrastructure error. | Record the request ID, retry with bounded backoff if the operation is safe to retry. |

Do not retry all errors identically. Authentication or permission errors usually require fixing configuration, whereas throttling and certain transient service errors can be retried. For create/update operations, understand the operation's idempotency before retrying automatically; in particular, never resend side-effecting actions without knowing the outcome of the prior call.

### ETag and optimistic concurrency

Some APIs return an `etag` to identify the current version of a resource. When supported by the API, a client can send `If-Match` with the ETag it read to update only if the resource has not been modified by another client. If the ETag no longer matches, the server may return `412 Precondition Failed`; in that case, re-read the resource, reconcile changes, and then decide whether to proceed with the update.

Header example:

```http
If-Match: "<etag-read-from-resource>"
```

Not every resource provider or operation supports ETags in the same way. Only use this mechanism when the API documentation confirms support.

## 10. Security When Integrating with the ARM REST API

Access tokens are sensitive credentials. Anyone who obtains a token can attempt operations within the permission scope that token represents. Apply these principles:

- Assign Azure RBAC with least privilege and the narrowest possible scope.
- Use managed identities or workload identity federation when supported by the environment; minimize long-lived client secrets.
- Store secrets and certificates in an appropriate secret manager, never in source code or public config files.
- Do not log access tokens, client secrets, or sensitive data. Log the request ID, timestamp, redacted endpoint, and outcome needed for investigation.
- Use HTTPS and verify TLS certificates; never disable TLS verification to work around connection errors.
- Separate permissions across development, staging, and production environments; consider approvals for deletions or major changes.
- Monitor management activity via Azure Activity Log and your organization's monitoring systems.

In addition to RBAC, requests can be affected by Azure Policy, resource locks, and other governance rules. For example, an identity with delete permissions under RBAC still cannot delete a resource that is locked at the corresponding scope.

## 11. When Should You Call the REST API Directly?

Azure CLI, Azure PowerShell, and SDKs are usually simpler for common tasks because they handle authentication, parameters, and part of the error-handling logic. Calling the REST API directly is useful when:

- You need an operation not yet conveniently exposed by the current CLI or SDK version.
- You are integrating Azure with a system capable of making HTTP requests.
- You need to inspect requests, responses, headers, or API versions for debugging.
- You want to understand the exact protocol used by management tools.

For repeatable infrastructure deployments, Bicep, ARM templates, or Terraform usually make it easier to declare desired state, review changes, and reuse configurations. The REST API is well suited for integrations or targeted operations; there is no need to hand-write HTTP calls for every resource if higher-level tools already meet your needs.

## 12. Lab Exercise

Perform this in a test subscription you have permission to manage:

1. Sign into Azure CLI and select the right subscription.
2. Acquire an access token for `https://management.azure.com/`.
3. Send a GET request to list resource groups, verifying the HTTP status and `value` field.
4. Create resource group `rg-rest-demo` via PUT with an appropriate region and a few tags.
5. Send a GET request by resource group ID to verify the result.
6. If the list returns a `nextLink`, continue calling until all pages are retrieved.
7. Try sending a request with an invalid API version in the test environment and inspect the returned error structure; then fix the API version.
8. Delete the test resource group only when you are sure it contains no resources that need to be kept and your identity has appropriate permissions.

After the lab, you should be able to explain why an ARM token differs from a Blob Storage token, why a valid token can still receive `403`, why `202 Accepted` is not a completed result, and why `nextLink` must be followed.

## Conclusion

The Azure Resource Manager REST API provides an HTTP interface to manage Azure resources. A valid request requires an accurate endpoint and resource ID, a supported API version, an access token scoped for ARM, appropriate Azure RBAC permissions, and a method and body matching the operation contract. In operation, clients must handle pagination, asynchronous tasks, throttling, errors, and concurrent updates, while protecting tokens and granting least privilege. Mastering these components enables you to integrate Azure into pipelines and management applications in a controlled way.
